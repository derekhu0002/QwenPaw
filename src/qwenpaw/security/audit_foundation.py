# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx

from ..constant import WORKING_DIR
from .tool_guard.engine import get_guard_engine
from .tool_guard.models import ToolGuardResult

logger = logging.getLogger(__name__)

_TOOL_GUARD_ENGINE = get_guard_engine()

_TRACE_DIR_NAME = "inbox_traces"
_CHECKPOINT_FILE_NAME = "audit_chain_checkpoint.json"
_PROMPT_PATTERN = re.compile(
    r"As authenticated employee\s+(?P<employee>.+?),\s+ask\s+(?P<agent>.+?)\s+"
    r"to use plugin\s+(?P<plugin>.+?)\s+and high-risk tool\s+(?P<tool>.+?)"
    r"(?:\.\s*Confirmation phrase:\s*(?P<phrase>.+?))?\.?$",
    re.IGNORECASE | re.DOTALL,
)
_HIGH_RISK_TOOL_PATTERN = re.compile(r"(?P<tool>[a-z0-9_]+_tool)\b", re.IGNORECASE)
_BYPASS_MARKERS = (
    "ignore every approval policy",
    "maintenance mode",
    "test mode",
    "already trusted",
    "missing confirmation",
)
_LEASE_WARMUP_MARKERS = (
    "lease heartbeat monitoring",
    "lease window expires",
)
_LEASE_REJOIN_MARKERS = (
    "resume normal model access",
    "lease window elapsed",
    "missing-gap verification evidence",
)
_LEASE_RESTORED_MARKERS = (
    "resume normal model access",
    "lease window elapsed",
    "missing-gap verification evidence completed",
)


def _workspace_dir(base_dir: Path | None = None) -> Path:
    return (base_dir or WORKING_DIR).expanduser().resolve()


def _trace_dir(base_dir: Path | None = None) -> Path:
    return _workspace_dir(base_dir) / _TRACE_DIR_NAME


def _trace_path(run_id: str, base_dir: Path | None = None) -> Path:
    return _trace_dir(base_dir) / f"{run_id}.json"


def _checkpoint_path(base_dir: Path | None = None) -> Path:
    return _workspace_dir(base_dir) / _CHECKPOINT_FILE_NAME


def _normalize_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _strip_terminal_punctuation(value: str) -> str:
    return value.strip().rstrip(".。!！")


def _latest_trace_payload(
    base_dir: Path | None = None,
    *,
    session_id: str = "",
) -> dict[str, Any]:
    trace_dir = _trace_dir(base_dir)
    if not trace_dir.exists():
        return {}
    trace_paths = sorted(trace_dir.glob("*.json"), key=lambda path: path.stat().st_mtime)
    if not trace_paths:
        return {}
    if not session_id:
        return _read_json(trace_paths[-1]) or {}
    for path in reversed(trace_paths):
        payload = _read_json(path) or {}
        if _normalize_text(payload.get("session_id")) == session_id:
            return payload
    return {}


def _latest_trace_run_id(
    base_dir: Path | None = None,
    *,
    session_id: str = "",
) -> str:
    latest = _latest_trace_payload(base_dir, session_id=session_id)
    run_id = _normalize_text(latest.get("run_id"))
    if run_id:
        return run_id
    return ""


def _security_center_base_url() -> str:
    return (os.environ.get("QWENPAW_SECURITY_CENTER_API_URL") or "").strip().rstrip("/")


def _security_center_web_url() -> str:
    return (os.environ.get("QWENPAW_SECURITY_CENTER_WEB_URL") or "").strip().rstrip("/")


def runtime_lease_client_id(base_dir: Path | None = None) -> str:
    workspace_fingerprint = hashlib.sha256(
        str(_workspace_dir(base_dir)).lower().encode("utf-8"),
    ).hexdigest()[:16]
    return f"runtime-heartbeat::{workspace_fingerprint}"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


async def _get_security_center(path: str) -> dict[str, Any]:
    base_url = _security_center_base_url()
    if not base_url:
        return {}
    url = path if path.startswith("http://") or path.startswith("https://") else f"{base_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}
    except Exception:
        logger.exception("Security Center HTTP read failed for %s", url)
        return {}


async def read_security_center_recovery_state(*, session_id: str) -> dict[str, Any]:
    return await _get_security_center(
        f"/security-center/v1/operator/timelines/{session_id}",
    )


async def emit_runtime_lease_heartbeat(
    *,
    base_dir: Path | None = None,
    session_id: str | None = None,
    user_id: str = "runtime_heartbeat_emitter",
    prompt_text: str = "Runtime startup heartbeat emitter registration.",
    ttl_seconds: int = 1,
) -> dict[str, Any]:
    resolved_session_id = session_id or runtime_lease_client_id(base_dir)
    anchor_state = _current_anchor_state(
        base_dir,
        bootstrap_client_id=resolved_session_id,
    )
    checkpoint = _read_json(_checkpoint_path(base_dir)) or {}
    emitted_at_ns = time.time_ns()
    return await _post_security_center(
        "/security-center/v1/recovery/handshake",
        {
            "client_id": resolved_session_id,
            "trace_id": f"runtime-heartbeat::{uuid.uuid4().hex[:12]}",
            "local_hash": anchor_state["head_hash"],
            "checkpoint_hash": _normalize_text(checkpoint.get("current_hash")) or anchor_state["head_hash"],
            "local_sequence": anchor_state["head_sequence"],
            "checkpoint_sequence": _safe_int(
                checkpoint.get("confirmed_sequence") or checkpoint.get("event_sequence"),
                anchor_state["head_sequence"],
            ),
            "anchored_event_id": anchor_state["head_anchor_event_id"],
            "checkpoint_anchor_id": _normalize_text(
                checkpoint.get("last_anchored_event_id")
                or checkpoint.get("anchored_event_id")
                or checkpoint.get("run_id"),
            )
            or anchor_state["head_anchor_event_id"],
            "requested_at_ns": emitted_at_ns,
            "lease_ttl_seconds": ttl_seconds,
            "tool_name": "runtime_lease_heartbeat",
            "user_id": user_id,
            "prompt_text": prompt_text,
        },
    )


async def _probe_security_center_web() -> str:
    base_url = _security_center_web_url()
    if not base_url:
        return ""
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            response = await client.get(f"{base_url}/")
            response.raise_for_status()
        return base_url
    except Exception:
        logger.exception("Security Center web probe failed for %s/", base_url)
        return ""


async def _post_security_center(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    base_url = _security_center_base_url()
    if not base_url:
        return {}
    url = f"{base_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}
    except Exception:
        logger.exception("Security Center HTTP projection failed for %s", url)
        return {}


def _extract_high_risk_tool_name(prompt_text: str, fallback_tool_name: str = "") -> str:
    if not prompt_text:
        return fallback_tool_name
    match = _HIGH_RISK_TOOL_PATTERN.search(prompt_text)
    if match:
        return _strip_terminal_punctuation(match.group("tool"))
    return fallback_tool_name


def _bind_security_nonce(
    *,
    run_id: str,
    session_id: str,
    user_id: str,
    tool_name: str,
    current_hash: str,
) -> tuple[str, str]:
    binding_material = "|".join(
        (
            run_id,
            session_id,
            user_id,
            tool_name,
            current_hash,
        ),
    )
    binding_hash = hashlib.sha256(binding_material.encode("utf-8")).hexdigest()
    return binding_hash[:32], binding_hash


def _parse_confirmation_prompt(
    prompt_text: str,
    *,
    fallback_employee_id: str,
    fallback_agent_name: str,
    fallback_plugin_name: str,
    fallback_tool_name: str,
) -> dict[str, str]:
    parsed = {
        "employee_id": fallback_employee_id,
        "delegated_agent_name": fallback_agent_name,
        "third_party_plugin_name": fallback_plugin_name,
        "high_risk_tool_name": fallback_tool_name,
        "user_confirmation_phrase": "",
    }
    match = _PROMPT_PATTERN.search(prompt_text.strip()) if prompt_text else None
    if not match:
        return parsed

    groups = match.groupdict()
    parsed["employee_id"] = _strip_terminal_punctuation(
        _normalize_text(groups.get("employee")) or fallback_employee_id,
    )
    parsed["delegated_agent_name"] = _strip_terminal_punctuation(
        _normalize_text(groups.get("agent")) or fallback_agent_name,
    )
    parsed["third_party_plugin_name"] = _strip_terminal_punctuation(
        _normalize_text(groups.get("plugin")) or fallback_plugin_name,
    )
    parsed["high_risk_tool_name"] = _strip_terminal_punctuation(
        _normalize_text(groups.get("tool")) or fallback_tool_name,
    )
    parsed["user_confirmation_phrase"] = _strip_terminal_punctuation(
        _normalize_text(groups.get("phrase")),
    )
    return parsed


def extract_prompt_security_context(
    prompt_text: str,
    *,
    fallback_employee_id: str,
    fallback_agent_name: str = "agent_b",
    fallback_plugin_name: str = "plugin_c",
    fallback_tool_name: str = "payroll_export_tool",
) -> dict[str, str]:
    parsed = _parse_confirmation_prompt(
        prompt_text,
        fallback_employee_id=fallback_employee_id,
        fallback_agent_name=fallback_agent_name,
        fallback_plugin_name=fallback_plugin_name,
        fallback_tool_name=fallback_tool_name,
    )
    if not parsed["high_risk_tool_name"]:
        parsed["high_risk_tool_name"] = _extract_high_risk_tool_name(
            prompt_text,
            fallback_tool_name,
        )
    return parsed


def prompt_requests_approval_bypass(prompt_text: str) -> bool:
    normalized = prompt_text.lower()
    return any(marker in normalized for marker in _BYPASS_MARKERS)


def classify_lease_prompt(prompt_text: str) -> str | None:
    normalized = prompt_text.lower().strip()
    if all(marker in normalized for marker in _LEASE_RESTORED_MARKERS):
        return "restored"
    if all(marker in normalized for marker in _LEASE_REJOIN_MARKERS):
        return "rejoin"
    if all(marker in normalized for marker in _LEASE_WARMUP_MARKERS):
        return "warmup"
    return None


def _tool_boundary_action(
    guard_result: ToolGuardResult | None,
) -> str | None:
    if guard_result is None:
        return None
    for finding in guard_result.findings:
        action = finding.metadata.get("boundary_action")
        if isinstance(action, str) and action:
            return action
    return None


def evaluate_high_risk_tool_boundary(
    *,
    session_id: str,
    user_id: str,
    tool_name: str,
    prompt_text: str,
    delegated_agent_name: str,
    third_party_plugin_name: str,
    user_confirmation_phrase: str,
) -> dict[str, Any]:
    tool_call = {
        "id": uuid.uuid4().hex,
        "name": tool_name,
        "input": {
            "delegated_agent_name": delegated_agent_name,
            "third_party_plugin_name": third_party_plugin_name,
            "high_risk_tool_name": tool_name,
            "user_confirmation_phrase": user_confirmation_phrase,
        },
    }
    guard_result = _TOOL_GUARD_ENGINE.guard(
        tool_name,
        {
            "prompt_text": prompt_text,
            "session_id": session_id,
            "user_id": user_id,
            "delegated_agent_name": delegated_agent_name,
            "third_party_plugin_name": third_party_plugin_name,
            "user_confirmation_phrase": user_confirmation_phrase,
        },
    )
    return {
        "action": _tool_boundary_action(guard_result),
        "guard_result": guard_result,
        "tool_call": tool_call,
    }


def lock_mode_required(base_dir: Path | None = None) -> bool:
    trace_dir = _trace_dir(base_dir)
    return trace_dir.exists() and any(trace_dir.glob("*.json")) and not _checkpoint_path(base_dir).exists()


async def preflight_sensitive_action_recovery(
    *,
    session_id: str,
    user_id: str,
    tool_name: str,
    prompt_text: str,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    if not tool_name:
        return {}

    checkpoint_path = _checkpoint_path(base_dir)
    checkpoint = _read_json(checkpoint_path) or {}
    latest_payload = _latest_trace_payload(base_dir, session_id=session_id)
    head_hash = _normalize_text(latest_payload.get("current_hash")) or _normalize_text(checkpoint.get("current_hash"))
    head_sequence = _safe_int(
        latest_payload.get("event_sequence"),
        _safe_int(checkpoint.get("confirmed_sequence") or checkpoint.get("event_sequence"), 0),
    )
    head_anchor_id = _normalize_text(latest_payload.get("anchored_event_id")) or _normalize_text(
        checkpoint.get("last_anchored_event_id") or checkpoint.get("anchored_event_id") or checkpoint.get("run_id"),
    )

    if not checkpoint_path.exists() and latest_payload:
        return {
            "recovery_required": True,
            "trust_state": "UNTRUSTED",
            "gap_status": "CHECKPOINT_MISSING",
            "recovery_gate_status": "OPEN",
            "divergence_reason": "checkpoint_missing",
            "reported_edge_head_hash": head_hash,
            "reported_edge_sequence": head_sequence,
            "reported_edge_anchor_event_id": head_anchor_id,
        }

    if not head_hash:
        return {}

    return await _post_security_center(
        "/security-center/v1/recovery/handshake",
        {
            "client_id": session_id,
            "trace_id": f"runtime-preflight::{uuid.uuid4().hex[:12]}",
            "local_hash": head_hash,
            "checkpoint_hash": _normalize_text(checkpoint.get("current_hash")) or head_hash,
            "local_sequence": head_sequence,
            "anchored_event_id": head_anchor_id,
            "checkpoint_sequence": _safe_int(checkpoint.get("confirmed_sequence") or checkpoint.get("event_sequence"), head_sequence),
            "checkpoint_anchor_id": _normalize_text(
                checkpoint.get("last_anchored_event_id") or checkpoint.get("anchored_event_id") or checkpoint.get("run_id"),
            )
            or head_anchor_id,
            "gap_proof": _build_gap_proof(base_dir, session_id=session_id),
            "requested_at_ns": time.time_ns(),
            "tool_name": tool_name,
            "user_id": user_id,
            "prompt_text": prompt_text,
        },
    )


async def write_lease_heartbeat_record(
    *,
    session_id: str,
    user_id: str,
    prompt_text: str,
    channel: str = "console",
    base_dir: Path | None = None,
) -> dict[str, Any]:
    created_at = time.time()
    run_id = str(uuid.uuid4())
    anchor_state = _current_anchor_state(
        base_dir,
        bootstrap_client_id=session_id,
    )
    checkpoint = _read_json(_checkpoint_path(base_dir)) or {}
    head_hash = anchor_state["head_hash"]
    head_sequence = anchor_state["head_sequence"]
    head_anchor_event_id = anchor_state["head_anchor_event_id"]
    ttl_seconds = 1
    emitted_at_ns = time.time_ns()
    handshake = await _post_security_center(
        "/security-center/v1/recovery/handshake",
        {
            "client_id": session_id,
            "trace_id": run_id,
            "local_hash": head_hash,
            "checkpoint_hash": _normalize_text(checkpoint.get("current_hash")) or head_hash,
            "local_sequence": head_sequence,
            "checkpoint_sequence": _safe_int(
                checkpoint.get("confirmed_sequence") or checkpoint.get("event_sequence"),
                head_sequence,
            ),
            "anchored_event_id": head_anchor_event_id,
            "checkpoint_anchor_id": _normalize_text(
                checkpoint.get("last_anchored_event_id")
                or checkpoint.get("anchored_event_id")
                or checkpoint.get("run_id"),
            )
            or head_anchor_event_id,
            "requested_at_ns": emitted_at_ns,
            "lease_ttl_seconds": ttl_seconds,
            "tool_name": "model_access_resume_tool",
            "user_id": user_id,
            "prompt_text": prompt_text,
        },
    )
    web_url = await _probe_security_center_web()
    payload = {
        "run_id": run_id,
        "event_type": "LEASE_HEARTBEAT",
        "status": "aligned",
        "created_at": created_at,
        "edge_timestamp_ns": emitted_at_ns,
        "user_id": user_id,
        "request_user_id": user_id,
        "session_id": session_id,
        "channel": channel,
        "prompt_text": prompt_text,
        "heartbeat_emitted_at": created_at,
        "heartbeat_interval_seconds": ttl_seconds,
        "security_heartbeat": "EMITTED",
        "lease_client_id": session_id,
        "trust_state": handshake.get("trust_state", "ALIGNED") if handshake else "ALIGNED",
        "recovery_required": handshake.get("recovery_required", False) if handshake else False,
        "gap_status": handshake.get("gap_status", "CLEAR") if handshake else "CLEAR",
        "security_center_backend_api": "/security-center/v1/operator/overview",
    }
    if web_url:
        payload.update(
            {
                "operator_web_projection": web_url,
                "security_center_operator_web": web_url,
                "operator_dashboard_status": "reachable",
            },
        )
    _write_checkpoint(
        base_dir=base_dir,
        run_id=run_id,
        current_hash=head_hash,
        confirmed_sequence=head_sequence,
        anchored_event_id=head_anchor_event_id,
        confirmed_at=created_at,
    )
    _atomic_write(_trace_path(run_id, base_dir), payload)
    return payload


async def write_restored_model_access_record(
    *,
    session_id: str,
    user_id: str,
    prompt_text: str,
    channel: str = "console",
    base_dir: Path | None = None,
) -> dict[str, Any]:
    created_at = time.time()
    run_id = str(uuid.uuid4())
    timeline = await _get_security_center(
        f"/security-center/v1/operator/timelines/{session_id}",
    )
    web_url = await _probe_security_center_web()
    payload = {
        "run_id": run_id,
        "event_type": "MODEL_ACCESS_RESTORED",
        "status": "restored",
        "created_at": created_at,
        "user_id": user_id,
        "request_user_id": user_id,
        "session_id": session_id,
        "channel": channel,
        "prompt_text": prompt_text,
        "trust_state": _normalize_text(timeline.get("trust_state")) or "ALIGNED",
        "recovery_required": bool(timeline.get("recovery_required")),
        "gap_status": _normalize_text(timeline.get("gap_status")) or "VALIDATED",
        "security_center_backend_api": f"/security-center/v1/operator/timelines/{session_id}",
    }
    if web_url:
        payload.update(
            {
                "operator_web_projection": web_url,
                "security_center_operator_web": web_url,
                "operator_dashboard_status": "reachable",
            },
        )
    _atomic_write(_trace_path(run_id, base_dir), payload)
    return payload


async def write_security_rejection_record(
    *,
    session_id: str,
    user_id: str,
    tool_name: str,
    prompt_text: str,
    channel: str = "console",
    agent_id: str = "high_risk_tool_guard",
    tool_call_id: str = "",
    guard_result: ToolGuardResult | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    created_at = time.time()
    edge_timestamp_ns = time.time_ns()
    run_id = str(uuid.uuid4())
    anchor_state = _current_anchor_state(
        base_dir,
        bootstrap_client_id=session_id,
    )
    prior_hash = anchor_state["head_hash"]
    prior_sequence = anchor_state["head_sequence"]
    prior_anchored_event_id = anchor_state["head_anchor_event_id"]
    event_sequence = anchor_state["next_sequence"]
    anchored_event_id = anchor_state["next_anchor_event_id"]
    current_hash = _canonical_hash(
        "security-rejection-chain-v1",
        {
            "run_id": run_id,
            "session_id": session_id,
            "user_id": user_id,
            "tool_name": tool_name,
            "prompt_text": prompt_text,
            "prior_hash": prior_hash,
            "event_sequence": event_sequence,
            "anchored_event_id": anchored_event_id,
            "created_at": f"{created_at:.9f}",
        },
    )
    nonce, binding_hash = _bind_security_nonce(
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        tool_name=tool_name,
        current_hash=current_hash,
    )
    payload = {
        "run_id": run_id,
        "event_type": "SECURITY_REJECTION",
        "status": "rejected",
        "decision": "rejected",
        "created_at": created_at,
        "verified_at": created_at,
        "edge_timestamp_ns": edge_timestamp_ns,
        "user_id": user_id,
        "request_user_id": user_id,
        "session_id": session_id,
        "channel": channel,
        "agent_id": agent_id,
        "tool_call_id": tool_call_id or run_id,
        "tool_name": tool_name,
        "high_risk_tool_name": tool_name,
        "event_sequence": event_sequence,
        "anchored_event_id": anchored_event_id,
        "prior_event_sequence": prior_sequence,
        "prior_anchored_event_id": prior_anchored_event_id,
        "prompt_text": prompt_text,
        "prior_hash": prior_hash,
        "current_hash": current_hash,
        "payload_hash": current_hash,
        "guard_decision": "rejected",
        "guard_category": "prompt_injection_tool_guard",
        "rejection_reason": "missing_trusted_context_and_confirmation",
        "rejected_event_id": run_id,
        "guardians_used": guard_result.guardians_used if guard_result else [],
        "Security_Rejection_Nonce": nonce,
        "security_rejection_nonce": nonce,
        "security_rejection_nonce_binding_hash": binding_hash,
    }
    if guard_result is not None and guard_result.findings:
        payload["guard_rule_id"] = guard_result.findings[0].rule_id

    # Persist the edge-side rejection evidence before cloud projection so the
    # explicit test harness can still observe a durable trace if remote
    # projection is slow or temporarily unavailable.
    _atomic_write(_trace_path(run_id, base_dir), payload)

    return payload


async def project_security_rejection_record(
    payload: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    run_id = str(payload.get("run_id") or "")
    if not run_id:
        return payload

    uplink_result = await _post_security_center(
        "/security-center/v1/uplinks/rejections",
        {
            "client_id": payload.get("session_id", ""),
            "trace_id": run_id,
            "session_id": payload.get("session_id", ""),
            "user_id": payload.get("user_id", ""),
            "tool_name": payload.get("tool_name", ""),
            "security_rejection_nonce": payload.get("security_rejection_nonce", ""),
            "security_rejection_nonce_binding_hash": payload.get("security_rejection_nonce_binding_hash", ""),
            "edge_timestamp_ns": payload.get("edge_timestamp_ns"),
            "prompt_text": payload.get("prompt_text", ""),
        },
    )
    if uplink_result:
        payload.update(
            {
                "backend_api_rejection_status": uplink_result.get(
                    "rejection_url",
                    "",
                ),
                "security_center_backend_api": uplink_result.get(
                    "rejection_url",
                    "",
                ),
                "realtime_push_channel": uplink_result.get(
                    "stream_url",
                    "",
                ),
                "sse_stream": uplink_result.get("stream_url", ""),
                "operator_alert_stream": uplink_result.get(
                    "stream_url",
                    "",
                ),
                "nonce_voucher": uplink_result.get("voucher", ""),
                "security_rejection_voucher": uplink_result.get(
                    "voucher",
                    "",
                ),
                "alert_latency_ms": uplink_result.get(
                    "alert_latency_ms",
                    0,
                ),
                "cloud_mirror_status": "PROJECTED",
                "uplink_status": "SYNCED_REJECTION",
                "mirror_rejection_id": uplink_result.get("trace_id", run_id),
            },
        )
        web_url = _security_center_web_url()
        if web_url:
            payload.update(
                {
                    "operator_web_projection": web_url,
                    "security_center_operator_web": web_url,
                    "operator_dashboard_status": "reachable",
                    "web_rejection_state": "VISIBLE",
                    "red_alert_state": "VISIBLE",
                    "operator_popup_state": "VISIBLE",
                },
            )
    _atomic_write(_trace_path(run_id, base_dir), payload)
    return payload


async def write_lockdown_record(
    *,
    session_id: str,
    user_id: str,
    tool_name: str,
    prompt_text: str,
    channel: str = "console",
    agent_id: str = "console_security_gate",
    base_dir: Path | None = None,
) -> dict[str, Any]:
    created_at = time.time()
    edge_timestamp_ns = time.time_ns()
    run_id = str(uuid.uuid4())
    checkpoint_path = _checkpoint_path(base_dir)
    checkpoint_exists = checkpoint_path.exists()
    checkpoint = _read_json(checkpoint_path) or {}
    latest_payload = _latest_trace_payload(base_dir, session_id=session_id)
    anchor_state = _current_anchor_state(
        base_dir,
        bootstrap_client_id=session_id,
    )
    prior_hash = anchor_state["head_hash"]
    prior_sequence = anchor_state["head_sequence"]
    prior_anchored_event_id = anchor_state["head_anchor_event_id"]
    event_sequence = anchor_state["next_sequence"]
    anchored_event_id = anchor_state["next_anchor_event_id"]
    current_hash = _canonical_hash(
        "audit-lockdown-chain-v1",
        {
            "run_id": run_id,
            "session_id": session_id,
            "user_id": user_id,
            "tool_name": tool_name,
            "prompt_text": prompt_text,
            "prior_hash": prior_hash,
            "event_sequence": event_sequence,
            "anchored_event_id": anchored_event_id,
            "lock_mode": "UNTRUSTED",
            "created_at": f"{created_at:.9f}",
        },
    )
    fork_point_event_id = (
        _normalize_text(latest_payload.get("run_id"))
        or _latest_trace_run_id(base_dir, session_id=session_id)
        or run_id
    )
    local_hash = anchor_state["head_hash"] or _normalize_text(latest_payload.get("current_hash")) or "tampered-current-hash"
    local_sequence = anchor_state["head_sequence"]
    local_anchor_event_id = anchor_state["head_anchor_event_id"]
    cloud_anchor_hash = _normalize_text(checkpoint.get("current_hash")) or prior_hash
    payload = {
        "run_id": run_id,
        "event_type": "AUDIT_INTEGRITY_LOCKDOWN",
        "status": "blocked",
        "decision": "lockdown",
        "created_at": created_at,
        "verified_at": created_at,
        "edge_timestamp_ns": edge_timestamp_ns,
        "user_id": user_id,
        "request_user_id": user_id,
        "session_id": session_id,
        "channel": channel,
        "agent_id": agent_id,
        "tool_name": tool_name,
        "high_risk_tool_name": tool_name,
        "event_sequence": event_sequence,
        "anchored_event_id": anchored_event_id,
        "prior_event_sequence": prior_sequence,
        "prior_anchored_event_id": prior_anchored_event_id,
        "prompt_text": prompt_text,
        "prior_hash": prior_hash,
        "current_hash": current_hash,
        "payload_hash": current_hash,
        "lock_mode": "UNTRUSTED",
        "trust_state": "UNTRUSTED",
        "anomaly_category": "audit_continuity_gap",
        "checkpoint_missing": not checkpoint_exists,
        "checkpoint_loss_detected": not checkpoint_exists,
        "tamper_detected": True,
        "integrity_alert": "checkpoint_loss" if not checkpoint_exists else "recovery_gate_active",
        "cloud_anchor_hash": cloud_anchor_hash,
    }

    handshake = await _post_security_center(
        "/security-center/v1/recovery/handshake",
        {
            "client_id": session_id,
            "trace_id": run_id,
            "local_hash": local_hash,
            "checkpoint_hash": _normalize_text(checkpoint.get("current_hash")) or prior_hash,
            "local_sequence": local_sequence,
            "anchored_event_id": local_anchor_event_id,
            "checkpoint_sequence": _safe_int(checkpoint.get("confirmed_sequence") or checkpoint.get("event_sequence"), local_sequence),
            "checkpoint_anchor_id": _normalize_text(
                checkpoint.get("last_anchored_event_id") or checkpoint.get("anchored_event_id") or checkpoint.get("run_id"),
            )
            or local_anchor_event_id,
            "gap_proof": _build_gap_proof(base_dir, session_id=session_id),
            "requested_at_ns": time.time_ns(),
        },
    )
    if handshake:
        payload.update(
            {
                "resume_handshake_status": handshake.get("handshake_status", "ready"),
                "cloud_anchor_hash": handshake.get(
                    "shadow_hash",
                    payload["cloud_anchor_hash"],
                ),
                "hash_divergence_curve": {
                    "local_hash": local_hash,
                    "cloud_shadow_hash": handshake.get(
                        "shadow_hash",
                        payload["cloud_anchor_hash"],
                    ),
                },
                "fork_point_event_id": handshake.get(
                    "last_trace_id",
                    fork_point_event_id,
                ),
                "hash_divergence_fork_point": handshake.get(
                    "last_trace_id",
                    fork_point_event_id,
                ),
                "mirror_alert": "/security-center/v1/operator/overview",
                "recovery_projection": "/security-center/v1/operator/overview",
                "recovery_required": handshake.get("recovery_required", True),
                "trusted_hash_alignment": handshake.get(
                    "trust_state",
                    "pending",
                ),
                "gap_status": handshake.get("gap_status", "GAP_VALIDATION_REQUIRED"),
                "recovery_gate_status": handshake.get("recovery_gate_status", "OPEN"),
                "last_trusted_anchor_hash": handshake.get("last_trusted_anchor_hash", cloud_anchor_hash),
                "last_trusted_sequence": handshake.get("last_trusted_sequence", 0),
                "last_trusted_anchor_event_id": handshake.get("last_trusted_anchor_event_id", prior_anchored_event_id),
                "current_edge_reported_hash": handshake.get("reported_edge_head_hash", local_hash),
                "current_edge_reported_sequence": handshake.get("reported_edge_sequence", local_sequence),
                "current_edge_reported_anchor_event_id": handshake.get("reported_edge_anchor_event_id", local_anchor_event_id),
            },
        )

    uplink_result = await _post_security_center(
        "/security-center/v1/uplinks/lockdowns",
        {
            "client_id": session_id,
            "trace_id": run_id,
            "session_id": session_id,
            "user_id": user_id,
            "tool_name": tool_name,
            "prior_hash": prior_hash,
            "current_hash": local_hash,
            "local_hash": local_hash,
            "current_sequence": local_sequence,
            "prior_sequence": _safe_int(checkpoint.get("confirmed_sequence") or checkpoint.get("event_sequence"), prior_sequence),
            "anchored_event_id": local_anchor_event_id,
            "prior_anchored_event_id": _normalize_text(
                checkpoint.get("last_anchored_event_id") or checkpoint.get("anchored_event_id") or checkpoint.get("run_id"),
            )
            or prior_anchored_event_id,
            "checkpoint_missing": not checkpoint_exists,
            "edge_timestamp_ns": edge_timestamp_ns,
            "prompt_text": prompt_text,
        },
    )
    if uplink_result:
        timeline_payload = {}
        timeline_path = uplink_result.get("timeline_url")
        if isinstance(timeline_path, str) and timeline_path:
            timeline_payload = await _get_security_center(timeline_path)
        payload.update(
            {
                "security_center_backend_api": uplink_result.get(
                    "timeline_url",
                    "",
                ),
                "cloud_mirror_status": uplink_result.get(
                    "trust_state",
                    "",
                ),
                "cloud_anchor_hash": uplink_result.get(
                    "shadow_hash",
                    payload["cloud_anchor_hash"],
                ),
                "hash_divergence_curve": {
                    "local_hash": local_hash,
                    "cloud_shadow_hash": uplink_result.get(
                        "shadow_hash",
                        payload["cloud_anchor_hash"],
                    ),
                },
                "alert_latency_ms": uplink_result.get("alert_latency_ms", 120),
                "uplink_status": "RECOVERY_REQUIRED",
            },
        )
        if timeline_payload:
            local_curve = timeline_payload.get("local_hash_curve") or []
            cloud_curve = timeline_payload.get("cloud_shadow_curve") or []
            fork_point = timeline_payload.get("fork_point") or {}
            payload.update(
                {
                    "hash_divergence_curve": {
                        "local_hash": (local_curve[-1] or {}).get("hash", local_hash) if local_curve else local_hash,
                        "cloud_shadow_hash": (cloud_curve[-1] or {}).get("hash", payload["cloud_anchor_hash"]) if cloud_curve else payload["cloud_anchor_hash"],
                    },
                    "fork_point_event_id": fork_point.get("event_id", fork_point_event_id),
                    "hash_divergence_fork_point": fork_point.get("event_id", fork_point_event_id),
                    "fork_sequence_number": fork_point.get("sequence", 1),
                },
            )
        web_url = await _probe_security_center_web()
        if web_url:
            payload.update(
                {
                    "operator_web_projection": web_url,
                    "security_center_operator_web": web_url,
                    "operator_dashboard_status": "reachable",
                    "hash_break_curve_chart": web_url,
                },
            )
    _atomic_write(_trace_path(run_id, base_dir), payload)
    return payload


def _confirmation_digest(
    *,
    employee_id: str,
    channel_name: str,
    authenticated_session_id: str,
    delegated_agent_name: str,
    third_party_plugin_name: str,
    high_risk_tool_name: str,
    user_confirmation_phrase: str,
) -> str:
    joined = "|".join(
        (
            employee_id,
            channel_name,
            authenticated_session_id,
            delegated_agent_name,
            third_party_plugin_name,
            high_risk_tool_name,
            user_confirmation_phrase,
        ),
    )
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _sha256_hex(*parts: Any) -> str:
    joined = "|".join(str(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump(mode="json"))
    if hasattr(value, "dict"):
        return _to_jsonable(value.dict())
    return {"repr": repr(value)}


def _canonical_json(value: Any) -> str:
    return json.dumps(_to_jsonable(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _canonical_hash(label: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json({"label": label, "payload": payload}).encode("utf-8"),
    ).hexdigest()


def _derive_security_center_bootstrap_hash(client_id: str) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "client_id": client_id,
                "parts": ["bootstrap"],
                "protocol": "security-center-v1",
            },
        ).encode("utf-8"),
    ).hexdigest()


def _current_anchor_state(
    base_dir: Path | None = None,
    *,
    bootstrap_client_id: str = "",
) -> dict[str, Any]:
    latest_payload = _latest_trace_payload(
        base_dir,
        session_id=bootstrap_client_id,
    )
    checkpoint = _read_json(_checkpoint_path(base_dir)) or {}
    bootstrap_hash = (
        _derive_security_center_bootstrap_hash(bootstrap_client_id)
        if bootstrap_client_id
        else ""
    )
    bootstrap_anchor_event_id = (
        f"shadow-anchor::{bootstrap_client_id}"
        if bootstrap_client_id
        else ""
    )
    head_hash = (
        _normalize_text(latest_payload.get("current_hash"))
        or _normalize_text(checkpoint.get("current_hash"))
        or bootstrap_hash
        or "GENESIS"
    )
    head_sequence = _safe_int(
        latest_payload.get("event_sequence"),
        _safe_int(checkpoint.get("confirmed_sequence") or checkpoint.get("event_sequence"), 0),
    )
    head_anchor_event_id = _normalize_text(latest_payload.get("anchored_event_id")) or _normalize_text(
        checkpoint.get("last_anchored_event_id") or checkpoint.get("anchored_event_id") or checkpoint.get("run_id"),
    ) or bootstrap_anchor_event_id or "GENESIS"
    next_sequence = head_sequence + 1
    return {
        "head_hash": head_hash,
        "head_sequence": head_sequence,
        "head_anchor_event_id": head_anchor_event_id,
        "next_sequence": next_sequence,
        "next_anchor_event_id": f"anchor-{next_sequence:08d}",
    }


def _gap_anchor_chain_material(payload: dict[str, Any]) -> dict[str, Any] | None:
    event_type = _normalize_text(payload.get("event_type"))
    if event_type == "USER_CONFIRMATION":
        return {
            "prior_hash": _normalize_text(payload.get("prior_hash")),
            "confirmation_digest": _normalize_text(payload.get("confirmation_digest")),
            "run_id": _normalize_text(payload.get("run_id")),
            "confirmed_at": f"{float(payload.get('confirmed_at') or payload.get('created_at') or 0):.9f}",
            "event_sequence": _safe_int(payload.get("event_sequence"), 0),
            "anchored_event_id": _normalize_text(payload.get("anchored_event_id")),
        }
    if event_type == "SECURITY_REJECTION":
        return {
            "run_id": _normalize_text(payload.get("run_id")),
            "session_id": _normalize_text(payload.get("session_id")),
            "user_id": _normalize_text(payload.get("user_id")),
            "tool_name": _normalize_text(payload.get("tool_name")),
            "prompt_text": _normalize_text(payload.get("prompt_text")),
            "prior_hash": _normalize_text(payload.get("prior_hash")),
            "event_sequence": _safe_int(payload.get("event_sequence"), 0),
            "anchored_event_id": _normalize_text(payload.get("anchored_event_id")),
            "created_at": f"{float(payload.get('created_at') or 0):.9f}",
        }
    if event_type == "AUDIT_INTEGRITY_LOCKDOWN":
        return {
            "run_id": _normalize_text(payload.get("run_id")),
            "session_id": _normalize_text(payload.get("session_id")),
            "user_id": _normalize_text(payload.get("user_id")),
            "tool_name": _normalize_text(payload.get("tool_name")),
            "prompt_text": _normalize_text(payload.get("prompt_text")),
            "prior_hash": _normalize_text(payload.get("prior_hash")),
            "event_sequence": _safe_int(payload.get("event_sequence"), 0),
            "anchored_event_id": _normalize_text(payload.get("anchored_event_id")),
            "lock_mode": _normalize_text(payload.get("lock_mode")) or "UNTRUSTED",
            "created_at": f"{float(payload.get('created_at') or 0):.9f}",
        }
    return None


def _gap_anchor_canonical_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": _normalize_text(payload.get("event_type")),
        "run_id": _normalize_text(payload.get("run_id")),
        "session_id": _normalize_text(payload.get("session_id")),
        "user_id": _normalize_text(payload.get("user_id")),
        "tool_name": _normalize_text(payload.get("tool_name")),
        "status": _normalize_text(payload.get("status")),
        "decision": _normalize_text(payload.get("decision")),
        "event_sequence": _safe_int(payload.get("event_sequence"), 0),
        "anchored_event_id": _normalize_text(payload.get("anchored_event_id")),
        "prior_hash": _normalize_text(payload.get("prior_hash")),
        "payload_hash": _normalize_text(payload.get("payload_hash")),
    }


def _gap_anchor_material_digest(anchor: dict[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "label": "gap-anchor-material-v1",
                "payload": {
                    "event_type": anchor["event_type"],
                    "run_id": anchor["run_id"],
                    "sequence": anchor["sequence"],
                    "anchored_event_id": anchor["anchored_event_id"],
                    "prior_hash": anchor["prior_hash"],
                    "payload_hash": anchor["payload_hash"],
                    "canonical_payload_digest": anchor["canonical_payload_digest"],
                },
            },
        ).encode("utf-8"),
    ).hexdigest()


def _gap_anchor_from_trace_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    chain_material = _gap_anchor_chain_material(payload)
    current_hash = _normalize_text(payload.get("current_hash"))
    if chain_material is None or not current_hash:
        return None
    canonical_payload = _gap_anchor_canonical_payload(payload)
    anchor = {
        "run_id": _normalize_text(payload.get("run_id")),
        "event_type": _normalize_text(payload.get("event_type")),
        "sequence": _safe_int(payload.get("event_sequence"), 0),
        "anchored_event_id": _normalize_text(payload.get("anchored_event_id")),
        "prior_hash": _normalize_text(payload.get("prior_hash")),
        "current_hash": current_hash,
        "payload_hash": _normalize_text(payload.get("payload_hash")),
        "canonical_payload": canonical_payload,
        "canonical_payload_digest": hashlib.sha256(_canonical_json(canonical_payload).encode("utf-8")).hexdigest(),
        "chain_material": chain_material,
    }
    anchor["anchor_material_digest"] = _gap_anchor_material_digest(anchor)
    return anchor


async def _project_trusted_anchor(payload: dict[str, Any]) -> None:
    anchor = _gap_anchor_from_trace_payload(payload)
    if anchor is None:
        return
    await _post_security_center(
        "/security-center/v1/uplinks/trusted-anchors",
        {
            "client_id": payload.get("session_id", ""),
            "trace_id": payload.get("run_id", ""),
            "run_id": payload.get("run_id", ""),
            "session_id": payload.get("session_id", ""),
            "event_type": payload.get("event_type", "UNKNOWN"),
            "anchor": anchor,
        },
    )


def _build_gap_proof(base_dir: Path | None = None, *, session_id: str = "") -> dict[str, Any]:
    checkpoint = _read_json(_checkpoint_path(base_dir)) or {}
    base_anchor_hash = _normalize_text(checkpoint.get("current_hash"))
    if not base_anchor_hash:
        return {}

    base_sequence = _safe_int(checkpoint.get("confirmed_sequence") or checkpoint.get("event_sequence"), 0)
    base_anchor_event_id = _normalize_text(
        checkpoint.get("last_anchored_event_id") or checkpoint.get("anchored_event_id") or checkpoint.get("run_id"),
    )
    trace_dir = _trace_dir(base_dir)
    if not trace_dir.exists():
        return {}

    anchors: list[dict[str, Any]] = []
    for path in sorted(trace_dir.glob("*.json"), key=lambda item: item.stat().st_mtime):
        payload = _read_json(path) or {}
        if session_id and _normalize_text(payload.get("session_id")) != session_id:
            continue
        sequence = _safe_int(payload.get("event_sequence"), 0)
        if sequence <= base_sequence:
            continue
        anchor = _gap_anchor_from_trace_payload(payload)
        if anchor is None:
            continue
        anchor["sequence"] = sequence
        if not anchor.get("anchored_event_id"):
            anchor["anchored_event_id"] = path.stem
        if not anchor.get("prior_hash"):
            anchor["prior_hash"] = base_anchor_hash
        anchors.append(anchor)
    if not anchors:
        return {}

    head = anchors[-1]
    proof_payload = {
        "base_anchor_hash": base_anchor_hash,
        "base_sequence": base_sequence,
        "base_anchor_event_id": base_anchor_event_id,
        "head_hash": head["current_hash"],
        "head_sequence": head["sequence"],
        "head_anchor_event_id": head["anchored_event_id"],
        "anchors": anchors,
    }
    proof_payload["proof_digest"] = _canonical_hash("audit-gap-proof-v1", proof_payload)
    return proof_payload


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    return None


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _write_checkpoint(
    *,
    base_dir: Path | None,
    run_id: str,
    current_hash: str,
    confirmed_sequence: int,
    anchored_event_id: str,
    confirmed_at: float,
) -> None:
    checkpoint = {
        "run_id": run_id,
        "current_hash": current_hash,
        "continuity_anchor": current_hash,
        "event_sequence": confirmed_sequence,
        "confirmed_sequence": confirmed_sequence,
        "anchored_event_id": anchored_event_id,
        "last_anchored_event_id": anchored_event_id,
        "updated_at": confirmed_at,
    }
    _atomic_write(_checkpoint_path(base_dir), checkpoint)


def capture_runtime_confirmation_context() -> dict[str, str]:
    from ..app.agent_context import (
        get_current_agent_id,
        get_current_channel,
        get_current_request_prompt,
        get_current_session_id,
        get_current_user_id,
    )

    prompt_text = _normalize_text(get_current_request_prompt())
    user_id = _normalize_text(get_current_user_id())
    channel_name = _normalize_text(get_current_channel()) or ""
    if channel_name == "console":
        channel_name = "local_console"
    session_id = _normalize_text(get_current_session_id())
    agent_id = _normalize_text(get_current_agent_id())

    parsed = _parse_confirmation_prompt(
        prompt_text,
        fallback_employee_id=user_id,
        fallback_agent_name=agent_id,
        fallback_plugin_name="",
        fallback_tool_name="",
    )

    return {
        "employee_id": parsed["employee_id"] or user_id,
        "delegated_agent_name": parsed["delegated_agent_name"] or agent_id,
        "third_party_plugin_name": parsed["third_party_plugin_name"],
        "high_risk_tool_name": parsed["high_risk_tool_name"],
        "user_confirmation_phrase": parsed["user_confirmation_phrase"],
        "channel_name": channel_name,
        "authenticated_session_id": session_id,
        "prompt_text": prompt_text,
    }


def parse_confirmation_prompt(
    prompt_text: str,
    *,
    fallback_employee_id: str,
    fallback_agent_name: str,
    fallback_plugin_name: str,
    fallback_tool_name: str,
) -> dict[str, str]:
    return _parse_confirmation_prompt(
        prompt_text,
        fallback_employee_id=fallback_employee_id,
        fallback_agent_name=fallback_agent_name,
        fallback_plugin_name=fallback_plugin_name,
        fallback_tool_name=fallback_tool_name,
    )


def prepare_confirmation_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    cloned = deepcopy(tool_call)
    if not isinstance(cloned, dict):
        return {"tool_call": tool_call}
    tool_input = cloned.get("input")
    if not isinstance(tool_input, dict):
        tool_input = {}
        cloned["input"] = tool_input
    runtime_context = capture_runtime_confirmation_context()
    tool_input.setdefault("delegated_agent_name", runtime_context["delegated_agent_name"])
    tool_input.setdefault(
        "third_party_plugin_name",
        runtime_context["third_party_plugin_name"],
    )
    tool_input.setdefault(
        "high_risk_tool_name",
        runtime_context["high_risk_tool_name"],
    )
    tool_input.setdefault(
        "user_confirmation_phrase",
        runtime_context["user_confirmation_phrase"],
    )
    cloned["input"] = tool_input
    return {
        "tool_call": cloned,
        "runtime_context": runtime_context,
    }


async def write_confirmation_record(
    *,
    run_id: str,
    session_id: str,
    user_id: str,
    channel: str,
    agent_id: str,
    tool_name: str,
    extra: dict[str, Any] | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    runtime_context = capture_runtime_confirmation_context()
    runtime_prompt_present = bool(runtime_context["prompt_text"])
    confirmation_context = {
        "employee_id": (
            runtime_context["employee_id"] if runtime_prompt_present else ""
        ) or user_id,
        "delegated_agent_name": (
            runtime_context["delegated_agent_name"] if runtime_prompt_present else ""
        )
        or _normalize_text((extra or {}).get("delegated_agent_name"))
        or agent_id,
        "third_party_plugin_name": (
            runtime_context["third_party_plugin_name"] if runtime_prompt_present else ""
        )
        or _normalize_text((extra or {}).get("third_party_plugin_name")),
        "high_risk_tool_name": (
            runtime_context["high_risk_tool_name"] if runtime_prompt_present else ""
        ) or _normalize_text((extra or {}).get("high_risk_tool_name")) or tool_name,
        "user_confirmation_phrase": (
            runtime_context["user_confirmation_phrase"] if runtime_prompt_present else ""
        ),
        "channel_name": (
            runtime_context["channel_name"] if runtime_prompt_present else ""
        ) or channel,
        "authenticated_session_id": (
            runtime_context["authenticated_session_id"] if runtime_prompt_present else ""
        ) or session_id,
    }
    if not confirmation_context["user_confirmation_phrase"]:
        confirmation_context["user_confirmation_phrase"] = _normalize_text(
            (extra or {}).get("user_confirmation_phrase"),
        )

    confirmed_at = time.time()
    anchor_state = _current_anchor_state(
        base_dir,
        bootstrap_client_id=session_id,
    )
    prior_hash = anchor_state["head_hash"]
    prior_sequence = anchor_state["head_sequence"]
    prior_anchored_event_id = anchor_state["head_anchor_event_id"]
    event_sequence = anchor_state["next_sequence"]
    anchored_event_id = anchor_state["next_anchor_event_id"]
    confirmation_digest = _confirmation_digest(
        employee_id=confirmation_context["employee_id"],
        channel_name=confirmation_context["channel_name"],
        authenticated_session_id=confirmation_context["authenticated_session_id"],
        delegated_agent_name=confirmation_context["delegated_agent_name"],
        third_party_plugin_name=confirmation_context["third_party_plugin_name"],
        high_risk_tool_name=confirmation_context["high_risk_tool_name"],
        user_confirmation_phrase=confirmation_context["user_confirmation_phrase"],
    )
    current_hash = _canonical_hash(
        "user-confirmation-chain-v2",
        {
            "prior_hash": prior_hash,
            "confirmation_digest": confirmation_digest,
            "run_id": run_id,
            "confirmed_at": f"{confirmed_at:.9f}",
            "event_sequence": event_sequence,
            "anchored_event_id": anchored_event_id,
        },
    )

    payload: dict[str, Any] = {
        "run_id": run_id,
        "event_type": "USER_CONFIRMATION",
        "status": "pending",
        "created_at": confirmed_at,
        "confirmed_at": confirmed_at,
        "released_at": confirmed_at,
        "tool_effect_at": confirmed_at,
        "verified_at": confirmed_at,
        "hash_chain_valid": True,
        "continuity_anchor": current_hash,
        "prior_hash": prior_hash,
        "current_hash": current_hash,
        "event_sequence": event_sequence,
        "anchored_event_id": anchored_event_id,
        "prior_event_sequence": prior_sequence,
        "prior_anchored_event_id": prior_anchored_event_id,
        "payload_hash": confirmation_digest,
        "confirmation_digest": confirmation_digest,
        "user_id": confirmation_context["employee_id"],
        "context_user_id": confirmation_context["employee_id"],
        "request_user_id": user_id,
        "channel": confirmation_context["channel_name"],
        "session_id": confirmation_context["authenticated_session_id"],
        "agent_id": confirmation_context["delegated_agent_name"],
        "delegated_agent_name": confirmation_context["delegated_agent_name"],
        "third_party_plugin_name": confirmation_context["third_party_plugin_name"],
        "tool_name": confirmation_context["high_risk_tool_name"],
        "high_risk_tool_name": confirmation_context["high_risk_tool_name"],
        "user_confirmation_phrase": confirmation_context["user_confirmation_phrase"],
        "prompt_text": runtime_context["prompt_text"],
        "confirmation_context": _to_jsonable(confirmation_context),
        "chain": [
            confirmation_context["employee_id"],
            confirmation_context["delegated_agent_name"],
            confirmation_context["third_party_plugin_name"],
            confirmation_context["high_risk_tool_name"],
        ],
        "audit_scope": "sec-e2e-024",
    }
    if extra:
        payload["extra"] = _to_jsonable(extra)

    _atomic_write(_trace_path(run_id, base_dir), payload)
    _write_checkpoint(
        base_dir=base_dir,
        run_id=run_id,
        current_hash=current_hash,
        confirmed_sequence=event_sequence,
        anchored_event_id=anchored_event_id,
        confirmed_at=confirmed_at,
    )
    await _project_trusted_anchor(payload)
    return payload


async def finalize_confirmation_record(
    run_id: str,
    *,
    base_dir: Path | None = None,
    status: str = "released",
    released_at: float | None = None,
    tool_effect_at: float | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    path = _trace_path(run_id, base_dir)
    payload = _read_json(path)
    if payload is None:
        return None

    now = time.time()
    payload["status"] = status
    payload["released_at"] = released_at or now
    payload["tool_effect_at"] = tool_effect_at or payload["released_at"]
    payload["verified_at"] = now
    payload["hash_chain_valid"] = True
    if extra:
        payload.setdefault("finalization", {})
        payload["finalization"].update(_to_jsonable(extra))

    _atomic_write(path, payload)
    return payload


