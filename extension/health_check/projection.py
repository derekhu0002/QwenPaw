# -*- coding: utf-8 -*-
"""Doctor-derived Health Check projection for Settings/Security."""
from __future__ import annotations

import asyncio
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

from qwenpaw.__version__ import __version__
from qwenpaw.cli import doctor_checks
from qwenpaw.cli.doctor_connectivity import collect_deep_channel_connectivity_notes
from qwenpaw.config import load_config
from qwenpaw.config.utils import strict_validate_config_file

def _doctor_projection_item(
    *,
    group: str,
    item_id: str,
    status: str,
    detail: str,
    risk: str = "",
    recommendation: str = "",
    fix_id: str | None = None,
    deep_only: bool = False,
) -> dict[str, Any]:
    """Build one Settings/Security doctor projection item."""

    return {
        "group": group,
        "id": item_id,
        "label": item_id,
        "status": status,
        "detail": detail,
        "risk": risk,
        "recommendation": recommendation,
        "fix_id": fix_id,
        "deep_only": deep_only,
    }


def _status_from_ok(ok: bool, *, note_only: bool = False) -> str:
    if ok:
        return "ok"
    return "suggestion" if note_only else "risk"


def _notes_detail(notes: list[str], ok_detail: str) -> tuple[str, str, str]:
    if notes:
        detail = "\n".join(notes)
        return "suggestion", detail, detail
    return "ok", ok_detail, ""


def _skip_item(group: str, item_id: str, reason: str) -> dict[str, Any]:
    return _doctor_projection_item(
        group=group,
        item_id=item_id,
        status="skipped",
        detail=reason,
        recommendation="Fix root config.json, then rerun Health Check.",
    )


def _config_dependent_skips(reason: str) -> tuple[dict[str, Any], ...]:
    specs = (
        ("agents", "agent-workspaces"),
        ("agents", "agent-json-profiles"),
        ("agents", "enabled-agent-config-load"),
        ("channels", "enabled-channel-credentials"),
        ("mcp-clients", "mcp-stdio-command"),
        ("mcp-clients", "mcp-http-sse-url"),
        ("skills", "enabled-skill-layout"),
        ("browser-playwright", "browser-playwright-dependencies"),
        ("security-baseline", "security-baseline-posture"),
        ("memory-embedding", "memory-embedding-config"),
        ("workspace-hygiene", "workspace-hygiene"),
        ("cron", "cron-jobs-json"),
        ("startup-paths", "workspace-writable"),
        ("startup-paths", "extra-volume-disk-space"),
        ("providers", "provider-configuration"),
        ("per-agent-models", "enabled-agent-model-connectivity"),
        ("api-target", "api-target-mismatch"),
    )
    return tuple(_skip_item(group, item_id, reason) for group, item_id in specs)


def _append_config_projection(
    items: list[dict[str, Any]],
    *,
    deep: bool,
    timeout: float,
    llm_timeout: float,
) -> None:
    config_ok, config_detail = strict_validate_config_file()
    items.append(
        _doctor_projection_item(
            group="config",
            item_id="root-config-json",
            status=_status_from_ok(config_ok),
            detail=config_detail,
            risk="" if config_ok else config_detail,
            recommendation=(
                "" if config_ok else "Fix the root config.json schema errors shown by qwenpaw doctor."
            ),
        ),
    )

    raw_cfg = doctor_checks.load_raw_config_dict()
    unknown = doctor_checks.scan_unknown_config_keys(raw_cfg) if raw_cfg is not None else []
    unknown_detail = "\n".join(unknown) if unknown else "no unknown root config keys"
    items.append(
        _doctor_projection_item(
            group="config",
            item_id="unknown-config-keys",
            status="suggestion" if unknown else "ok",
            detail=unknown_detail,
            risk=unknown_detail if unknown else "",
            recommendation=(
                "Review obsolete config.json keys manually; doctor does not remove them."
                if unknown
                else ""
            ),
        ),
    )

    if not config_ok:
        items.extend(_config_dependent_skips("root config.json did not validate"))
        return

    try:
        cfg = load_config()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        items.extend(_config_dependent_skips(f"load_config failed: {exc}"))
        return

    legacy = doctor_checks.legacy_single_agent_workspace_note(cfg)
    ws_ok, ws_detail = doctor_checks.check_agent_profile_workspaces(cfg)
    if legacy:
        ws_detail = f"{ws_detail}\n{legacy}"
    items.append(
        _doctor_projection_item(
            group="agents",
            item_id="agent-workspaces",
            status=_status_from_ok(ws_ok),
            detail=ws_detail,
            risk="" if ws_ok else ws_detail,
            recommendation=(
                "" if ws_ok else "Run a confirmed doctor fix for ensure-workspace-dirs if paths are under working_dir."
            ),
            fix_id=None if ws_ok else "ensure-workspace-dirs",
        ),
    )

    aj_ok, aj_detail = doctor_checks.check_agent_json_profiles(cfg)
    items.append(
        _doctor_projection_item(
            group="agents",
            item_id="agent-json-profiles",
            status=_status_from_ok(aj_ok),
            detail=aj_detail,
            risk="" if aj_ok else aj_detail,
            recommendation="" if aj_ok else "Seed or reset invalid agent.json files after reviewing the plan.",
            fix_id=None if aj_ok else "seed-missing-agent-json",
        ),
    )

    acl_ok, acl_detail = doctor_checks.check_enabled_agents_load_agent_config(cfg)
    items.append(
        _doctor_projection_item(
            group="agents",
            item_id="enabled-agent-config-load",
            status=_status_from_ok(acl_ok),
            detail=acl_detail,
            risk="" if acl_ok else acl_detail,
            recommendation="" if acl_ok else "Repair enabled agent config load failures before startup.",
            fix_id=None if acl_ok else "seed-missing-agent-json",
        ),
    )

    status, detail, risk = _notes_detail(
        doctor_checks.enabled_channel_notes(cfg),
        "no enabled-channel credential warnings",
    )
    items.append(
        _doctor_projection_item(
            group="channels",
            item_id="enabled-channel-credentials",
            status=status,
            detail=detail,
            risk=risk,
            recommendation="Complete credentials for enabled channels." if risk else "",
        ),
    )

    if deep:
        conn_notes = collect_deep_channel_connectivity_notes(cfg, timeout)
        status, detail, risk = _notes_detail(
            conn_notes,
            "no connectivity warnings for enabled channels",
        )
        items.append(
            _doctor_projection_item(
                group="channels",
                item_id="enabled-channel-connectivity",
                status=status,
                detail=detail,
                risk=risk,
                recommendation="Review network reachability for enabled channels." if risk else "",
                deep_only=True,
            ),
        )

    mcp_notes = doctor_checks.mcp_client_notes(cfg)
    mcp_status, mcp_detail, mcp_risk = _notes_detail(mcp_notes, "no MCP client warnings")
    items.append(
        _doctor_projection_item(
            group="mcp-clients",
            item_id="mcp-stdio-command",
            status=mcp_status,
            detail=mcp_detail,
            risk=mcp_risk,
            recommendation="Fix enabled stdio MCP commands on PATH." if mcp_risk else "",
        ),
    )
    items.append(
        _doctor_projection_item(
            group="mcp-clients",
            item_id="mcp-http-sse-url",
            status=mcp_status,
            detail=mcp_detail,
            risk=mcp_risk,
            recommendation="Fix enabled HTTP/SSE MCP URLs." if mcp_risk else "",
        ),
    )

    status, detail, risk = _notes_detail(
        doctor_checks.skill_layout_notes(cfg),
        "no skill layout warnings",
    )
    items.append(
        _doctor_projection_item(
            group="skills",
            item_id="enabled-skill-layout",
            status=status,
            detail=detail,
            risk=risk,
            recommendation="Reconcile enabled skills with workspace skill directories." if risk else "",
            fix_id="reconcile-workspace-skills" if risk else None,
        ),
    )

    for group, item_id, notes_fn, ok_detail, rec in (
        (
            "browser-playwright",
            "browser-playwright-dependencies",
            doctor_checks.browser_automation_notes,
            "no browser automation warnings",
            "Install or configure Playwright/Chromium for browser automation.",
        ),
        (
            "security-baseline",
            "security-baseline-posture",
            doctor_checks.security_baseline_notes,
            "no baseline warnings",
            "Review disabled security controls before production use.",
        ),
        (
            "memory-embedding",
            "memory-embedding-config",
            doctor_checks.memory_embedding_notes,
            "no embedding warnings",
            "Configure embedding credentials for enabled memory search.",
        ),
        (
            "workspace-hygiene",
            "workspace-hygiene",
            doctor_checks.workspace_hygiene_notes,
            "no hygiene warnings",
            "Clean large workspace files or accumulated tool/dialog outputs.",
        ),
    ):
        status, detail, risk = _notes_detail(notes_fn(cfg), ok_detail)
        items.append(
            _doctor_projection_item(
                group=group,
                item_id=item_id,
                status=status,
                detail=detail,
                risk=risk,
                recommendation=rec if risk else "",
            ),
        )

    cj_ok, cj_detail = doctor_checks.check_cron_jobs_files(cfg)
    items.append(
        _doctor_projection_item(
            group="cron",
            item_id="cron-jobs-json",
            status=_status_from_ok(cj_ok),
            detail=cj_detail,
            risk="" if cj_ok else cj_detail,
            recommendation="" if cj_ok else "Validate and normalize jobs.json through doctor fix after review.",
            fix_id=None if cj_ok else "validate-all-jobs-json",
        ),
    )

    ws_w_ok, ws_w_detail = doctor_checks.check_agent_workspace_writable(cfg)
    items.append(
        _doctor_projection_item(
            group="startup-paths",
            item_id="workspace-writable",
            status=_status_from_ok(ws_w_ok),
            detail=ws_w_detail,
            risk="" if ws_w_ok else ws_w_detail,
            recommendation="" if ws_w_ok else "Fix filesystem permissions on listed workspace paths.",
        ),
    )

    vol_notes = doctor_checks.startup_extra_volume_disk_notes(cfg)
    status, detail, risk = _notes_detail(vol_notes, "no extra-volume disk warnings")
    items.append(
        _doctor_projection_item(
            group="startup-paths",
            item_id="extra-volume-disk-space",
            status=status,
            detail=detail,
            risk=risk,
            recommendation="Free space on persistence volumes outside working_dir." if risk else "",
        ),
    )

    try:
        prov_notes = doctor_checks.provider_overview_notes()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        prov_notes = [f"could not list providers: {exc}"]
    status, detail, risk = _notes_detail(
        prov_notes,
        "no custom provider configuration warnings",
    )
    items.append(
        _doctor_projection_item(
            group="providers",
            item_id="provider-configuration",
            status=status,
            detail=detail,
            risk=risk,
            recommendation="Complete provider API key and base URL settings." if risk else "",
        ),
    )

    try:
        aok, lines, extra_notes = asyncio.run(
            doctor_checks.check_enabled_agents_model_connections(
                cfg,
                timeout=llm_timeout,
                deep=deep,
            ),
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        aok, lines, extra_notes = False, [f"enabled agent model check failed: {exc}"], []
    detail = "\n".join((*lines, *extra_notes))
    items.append(
        _doctor_projection_item(
            group="per-agent-models",
            item_id="enabled-agent-model-connectivity",
            status=_status_from_ok(aok),
            detail=detail,
            risk="" if aok else detail,
            recommendation="" if aok else "Fix provider/model configuration for enabled agents.",
        ),
    )

    if deep:
        local_notes = doctor_checks.qwenpaw_local_llm_deep_notes()
        status, detail, risk = _notes_detail(
            local_notes,
            "no qwenpaw local LLM deep notes",
        )
        items.append(
            _doctor_projection_item(
                group="active-llm",
                item_id="qwenpaw-local-llm-deep",
                status=status,
                detail=detail,
                risk=risk,
                recommendation="Install or start llama.cpp local runtime if needed." if risk else "",
                deep_only=True,
            ),
        )

    mismatch = doctor_checks.api_target_mismatch_note(cfg, "http://127.0.0.1:8088")
    items.append(
        _doctor_projection_item(
            group="api-target",
            item_id="api-target-mismatch",
            status="suggestion" if mismatch else "ok",
            detail=mismatch or "CLI target matches persisted last_api or last_api is unset",
            risk=mismatch or "",
            recommendation="Use the same host/port as the running server." if mismatch else "",
        ),
    )


def _collect_doctor_projection_items(
    root: Path,
    *,
    deep: bool,
    timeout: float,
    llm_timeout: float,
) -> tuple[dict[str, Any], ...]:
    items: list[dict[str, Any]] = []

    env_lines = doctor_checks.environment_summary_lines()
    env_map = {
        line.split(":", 1)[0].strip(): line.split(":", 1)[1].strip()
        for line in env_lines
        if ":" in line
    }
    items.extend(
        (
            _doctor_projection_item(
                group="environment",
                item_id="python-version",
                status="ok",
                detail=env_map.get("python version", sys.version.split()[0]),
            ),
            _doctor_projection_item(
                group="environment",
                item_id="qwenpaw-version",
                status="ok",
                detail=__version__,
            ),
            _doctor_projection_item(
                group="environment",
                item_id="platform",
                status="ok",
                detail=env_map.get("platform", sys.platform),
            ),
            _doctor_projection_item(
                group="environment",
                item_id="sqlite-library",
                status="ok",
                detail=sqlite3.sqlite_version,
            ),
        ),
    )

    working_dir_ok = root.is_dir() and root.exists()
    items.append(
        _doctor_projection_item(
            group="environment",
            item_id="working-dir",
            status=_status_from_ok(working_dir_ok),
            detail=str(root),
            risk="" if working_dir_ok else f"missing: {root}",
            recommendation="" if working_dir_ok else "Create or initialize the QwenPaw working directory.",
            fix_id=None if working_dir_ok else "ensure-working-dir",
        ),
    )
    try:
        du = shutil.disk_usage(root if root.exists() else root.parent)
        free_gib = du.free / (1024**3)
        low_space = free_gib < 0.5
        items.append(
            _doctor_projection_item(
                group="environment",
                item_id="working-dir-disk-space",
                status="suggestion" if low_space else "ok",
                detail=f"{free_gib:.2f} GiB free on working_dir volume",
                risk="working_dir volume is below 0.5 GiB free" if low_space else "",
                recommendation="Free disk space before writes fail." if low_space else "",
            ),
        )
    except OSError as exc:
        items.append(
            _doctor_projection_item(
                group="environment",
                item_id="working-dir-disk-space",
                status="risk",
                detail=f"could not stat working_dir volume: {exc}",
                risk=str(exc),
                recommendation="Verify working_dir path and filesystem permissions.",
            ),
        )

    _append_config_projection(items, deep=deep, timeout=timeout, llm_timeout=llm_timeout)

    log_ok, log_detail = doctor_checks.check_app_log_writable()
    items.append(
        _doctor_projection_item(
            group="startup-paths",
            item_id="startup-log-writable",
            status=_status_from_ok(log_ok),
            detail=log_detail,
            risk="" if log_ok else log_detail,
            recommendation="" if log_ok else "Ensure the data directory and qwenpaw log path are writable.",
            fix_id=None if log_ok else "ensure-working-dir",
        ),
    )

    console_notes = doctor_checks.console_static_diagnostic_notes()
    console_missing = any("index.html missing" in line for line in console_notes)
    items.append(
        _doctor_projection_item(
            group="console-static-files",
            item_id="console-static-build",
            status="suggestion" if console_missing else "ok",
            detail="\n".join(console_notes) if console_notes else "console static diagnostics unavailable",
            risk="console static index.html is missing" if console_missing else "",
            recommendation="Build console/ or run a confirmed rebuild-console-npm doctor fix." if console_missing else "",
            fix_id="rebuild-console-npm" if console_missing else "ensure-working-dir",
        ),
    )

    items.append(
        _doctor_projection_item(
            group="web-authentication",
            item_id="web-authentication",
            status="ok",
            detail="web authentication configuration can be validated by qwenpaw doctor against the active API base URL",
            recommendation="Register the first web account if authentication is enabled and no users exist.",
        ),
    )

    return tuple(items)
