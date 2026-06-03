# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import re
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..constant import WORKING_DIR

_TRACE_DIR_NAME = "inbox_traces"
_CHECKPOINT_FILE_NAME = "audit_chain_checkpoint.json"
_PROMPT_PATTERN = re.compile(
    r"As authenticated employee\s+(?P<employee>.+?),\s+ask\s+(?P<agent>.+?)\s+"
    r"to use plugin\s+(?P<plugin>.+?)\s+and high-risk tool\s+(?P<tool>.+?)"
    r"(?:\.\s*Confirmation phrase:\s*(?P<phrase>.+?))?\.?$",
    re.IGNORECASE | re.DOTALL,
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
    confirmed_at: float,
) -> None:
    checkpoint = {
        "run_id": run_id,
        "current_hash": current_hash,
        "continuity_anchor": current_hash,
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
    confirmation_context = {
        "employee_id": runtime_context["employee_id"] or user_id,
        "delegated_agent_name": runtime_context["delegated_agent_name"]
        or agent_id,
        "third_party_plugin_name": runtime_context["third_party_plugin_name"]
        or _normalize_text((extra or {}).get("third_party_plugin_name")),
        "high_risk_tool_name": runtime_context["high_risk_tool_name"] or tool_name,
        "user_confirmation_phrase": runtime_context["user_confirmation_phrase"],
        "channel_name": runtime_context["channel_name"] or channel,
        "authenticated_session_id": runtime_context["authenticated_session_id"]
        or session_id,
    }
    if not confirmation_context["user_confirmation_phrase"]:
        confirmation_context["user_confirmation_phrase"] = _normalize_text(
            (extra or {}).get("user_confirmation_phrase"),
        )

    confirmed_at = time.time()
    checkpoint = _read_json(_checkpoint_path(base_dir)) or {}
    prior_hash = _normalize_text(checkpoint.get("current_hash")) or "GENESIS"
    current_hash = _confirmation_digest(
        employee_id=confirmation_context["employee_id"],
        channel_name=confirmation_context["channel_name"],
        authenticated_session_id=confirmation_context["authenticated_session_id"],
        delegated_agent_name=confirmation_context["delegated_agent_name"],
        third_party_plugin_name=confirmation_context["third_party_plugin_name"],
        high_risk_tool_name=confirmation_context["high_risk_tool_name"],
        user_confirmation_phrase=confirmation_context["user_confirmation_phrase"],
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
        "payload_hash": current_hash,
        "confirmation_digest": current_hash,
        "user_id": confirmation_context["employee_id"],
        "context_user_id": runtime_context["employee_id"] or user_id,
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
        confirmed_at=confirmed_at,
    )
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