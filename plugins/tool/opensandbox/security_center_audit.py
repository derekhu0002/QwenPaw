# -*- coding: utf-8 -*-
"""Security Center audit reporting for OpenSandbox MCP tool calls."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

_EVENT_PATH = "/security-center/v1/events"
_SOURCE_SYSTEM = "opensandbox"
_EVENT_TYPE_ID = "opensandbox"
_SCHEMA_VERSION = "1.0"
_MAX_TEXT_LENGTH = 512
_MAX_COLLECTION_ITEMS = 20
_MAX_ARGUMENT_SUMMARY_CHARS = 4096
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "auth_password",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)
_CONTENT_KEYS = {"content", "old_content", "new_content", "data"}
_COMMAND_SECRET_PATTERNS = (
    re.compile(
        r"(?i)(--?(?:api[-_]?key|password|secret|token)\s+"
        r"(?:=\s*)?)([^\s]+)",
    ),
    re.compile(
        r"(?i)\b([A-Z0-9_]*(?:API_KEY|PASSWORD|SECRET|TOKEN))="
        r"([^\s]+)",
    ),
    re.compile(r"(?i)(authorization:\s*bearer\s+)([^\s]+)"),
)

_READ_TOOLS = {
    "file_read",
    "file_search",
    "sandbox_get_info",
    "sandbox_get_metrics",
    "sandbox_healthcheck",
    "sandbox_list",
}
_EXECUTION_TOOLS = {"command_run", "command_interrupt"}
_FILE_WRITE_TOOLS = {
    "file_create_directories",
    "file_delete",
    "file_delete_directories",
    "file_move",
    "file_replace_contents",
    "file_write",
}
_LIFECYCLE_TOOLS = {
    "sandbox_connect",
    "sandbox_create",
    "sandbox_kill",
    "sandbox_renew",
}
_NETWORK_TOOLS = {"sandbox_get_endpoint"}


@dataclass(frozen=True)
class AuditConfig:
    """Runtime settings for Security Center event reporting."""

    security_center_url: str
    agent_id: str
    timeout_seconds: float = 2.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00",
        "Z",
    )


def _jsonable(value: Any) -> Any:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _jsonable(model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _digest(value: Any) -> str:
    serialized = json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _redact_text(value: str) -> str:
    redacted = value
    for pattern in _COMMAND_SECRET_PATTERNS:
        redacted = pattern.sub(r"\1[REDACTED]", redacted)
    if len(redacted) > _MAX_TEXT_LENGTH:
        return f"{redacted[:_MAX_TEXT_LENGTH]}...<truncated>"
    return redacted


def _content_descriptor(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        raw = value.encode("utf-8")
    elif isinstance(value, bytes):
        raw = value
    else:
        raw = json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    return {
        "length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _sanitize_value(value: Any, *, key: str = "", depth: int = 0) -> Any:
    if _is_sensitive_key(key):
        return "[REDACTED]"
    if key.lower() in _CONTENT_KEYS:
        return _content_descriptor(value)
    if key.lower() == "env" and isinstance(value, Mapping):
        return {"keys": sorted(str(item) for item in value.keys())}
    if depth >= 5:
        return "<max-depth>"
    if isinstance(value, Mapping):
        items = list(value.items())[:_MAX_COLLECTION_ITEMS]
        sanitized = {
            str(item_key): _sanitize_value(
                item_value,
                key=str(item_key),
                depth=depth + 1,
            )
            for item_key, item_value in items
        }
        if len(value) > _MAX_COLLECTION_ITEMS:
            sanitized["_truncatedItems"] = len(value) - _MAX_COLLECTION_ITEMS
        return sanitized
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        items = list(value)
        sanitized_items = [
            _sanitize_value(item, depth=depth + 1)
            for item in items[:_MAX_COLLECTION_ITEMS]
        ]
        if len(items) > _MAX_COLLECTION_ITEMS:
            sanitized_items.append(
                {"_truncatedItems": len(items) - _MAX_COLLECTION_ITEMS},
            )
        return sanitized_items
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, bytes):
        return _content_descriptor(value)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return _redact_text(str(value))


def summarize_arguments(
    tool_name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a bounded, secret-aware summary of MCP tool arguments."""
    summary = _sanitize_value(arguments)
    if not isinstance(summary, dict):
        summary = {"value": summary}
    if tool_name == "command_run" and isinstance(arguments.get("command"), str):
        command = str(arguments["command"])
        summary["command"] = {
            "preview": _redact_text(command),
            "sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
        }
    serialized = json.dumps(
        summary,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(serialized) > _MAX_ARGUMENT_SUMMARY_CHARS:
        return {
            "_truncated": True,
            "preview": serialized[:_MAX_TEXT_LENGTH],
            "sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        }
    return summary


def _operation_class(tool_name: str) -> str:
    if tool_name in _EXECUTION_TOOLS:
        return "EXECUTION"
    if tool_name in _FILE_WRITE_TOOLS:
        return "FILE_WRITE"
    if tool_name in _READ_TOOLS:
        return "READ"
    if tool_name in _LIFECYCLE_TOOLS:
        return "LIFECYCLE"
    if tool_name in _NETWORK_TOOLS:
        return "NETWORK"
    return "OTHER"


def _severity(succeeded: bool) -> str:
    if not succeeded:
        return "HIGH"
    return "DEBUG"


def _find_result_value(
    value: Any,
    keys: set[str],
    depth: int = 0,
) -> Any:
    if depth >= 5:
        return None
    normalized = _jsonable(value)
    if isinstance(normalized, Mapping):
        for key, item in normalized.items():
            if str(key) in keys and item is not None:
                return item
        for item in normalized.values():
            found = _find_result_value(item, keys, depth + 1)
            if found is not None:
                return found
    elif isinstance(normalized, list):
        for item in normalized:
            found = _find_result_value(item, keys, depth + 1)
            if found is not None:
                return found
    return None


class SecurityCenterAuditReporter:
    """Build and submit OpenSandbox audit events to Security Center."""

    def __init__(self, config: AuditConfig) -> None:
        self._config = config
        self._launcher_instance_id = uuid.uuid4().hex

    @property
    def endpoint(self) -> str:
        base = self._config.security_center_url.rstrip("/")
        if base.endswith(_EVENT_PATH):
            return base
        return f"{base}{_EVENT_PATH}"

    def build_event(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, Any],
        duration_ms: int,
        result: Any = None,
        error: BaseException | None = None,
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        execution_id = _find_result_value(
            result,
            {"execution_id", "executionId", "id"},
        )
        exit_code = _find_result_value(result, {"exit_code", "exitCode"})
        command_failed = (
            tool_name == "command_run"
            and exit_code is not None
            and str(exit_code) != "0"
        )
        succeeded = error is None and not command_failed
        outcome = "succeeded" if succeeded else "failed"
        sandbox_id = arguments.get("sandbox_id")
        if sandbox_id is None:
            sandbox_id = _find_result_value(result, {"sandbox_id", "sandboxId"})

        payload: dict[str, Any] = {
            "toolName": tool_name,
            "operationClass": _operation_class(tool_name),
            "outcome": outcome.upper(),
            "agentId": _redact_text(self._config.agent_id)[:128],
            "launcherInstanceId": self._launcher_instance_id,
            "durationMs": duration_ms,
            "requestDigest": _digest(arguments),
            "argumentSummary": summarize_arguments(tool_name, arguments),
        }
        if sandbox_id is not None:
            payload["sandboxId"] = _redact_text(str(sandbox_id))[:128]

        if tool_name == "command_run" and execution_id is not None:
            payload["executionId"] = _redact_text(str(execution_id))
        if tool_name == "command_run" and exit_code is not None:
            payload["exitCode"] = exit_code
        if command_failed:
            payload["failureReason"] = "nonzero_exit_code"
        if error is not None:
            payload["errorType"] = type(error).__name__
            payload["errorMessage"] = _redact_text(str(error))

        event: dict[str, Any] = {
            "sourceSystem": _SOURCE_SYSTEM,
            "eventId": f"opensandbox-{uuid.uuid4().hex}",
            "eventTypeId": _EVENT_TYPE_ID,
            "schemaVersion": _SCHEMA_VERSION,
            "severity": _severity(succeeded),
            "summary": f"OpenSandbox MCP {tool_name} {outcome}",
            "occurredAt": occurred_at or _utc_now_iso(),
            "payload": payload,
        }
        return event

    def send(self, event: Mapping[str, Any]) -> None:
        """Submit one event without retries or local persistence."""
        response = requests.post(
            self.endpoint,
            json=dict(event),
            timeout=self._config.timeout_seconds,
        )
        response.raise_for_status()


async def _build_and_report_without_affecting_tool_call(
    reporter: SecurityCenterAuditReporter,
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
    duration_ms: int,
    result: Any = None,
    error: BaseException | None = None,
) -> None:
    try:
        event = reporter.build_event(
            tool_name=tool_name,
            arguments=arguments,
            duration_ms=duration_ms,
            result=result,
            error=error,
        )
        await asyncio.to_thread(reporter.send, event)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "OpenSandbox Security Center audit reporting failed: %s",
            exc,
        )


def install_audit_hook(
    mcp: Any,
    reporter: SecurityCenterAuditReporter,
) -> None:
    """Wrap the FastMCP tool manager so every OpenSandbox call is audited."""
    tool_manager = getattr(mcp, "_tool_manager", None)
    original_call_tool = getattr(tool_manager, "call_tool", None)
    if not callable(original_call_tool):
        raise RuntimeError("OpenSandbox MCP tool manager is unavailable")
    if getattr(tool_manager, "_qwenpaw_security_center_audit", False):
        return

    async def audited_call_tool(
        name: str,
        arguments: dict[str, Any],
        context: Any = None,
        convert_result: bool = False,
    ) -> Any:
        started = time.perf_counter()
        try:
            result = await original_call_tool(
                name,
                arguments,
                context=context,
                convert_result=convert_result,
            )
        except Exception as exc:
            await _build_and_report_without_affecting_tool_call(
                reporter,
                tool_name=name,
                arguments=arguments,
                duration_ms=max(
                    0,
                    round((time.perf_counter() - started) * 1000),
                ),
                error=exc,
            )
            raise

        await _build_and_report_without_affecting_tool_call(
            reporter,
            tool_name=name,
            arguments=arguments,
            duration_ms=max(
                0,
                round((time.perf_counter() - started) * 1000),
            ),
            result=result,
        )
        return result

    setattr(tool_manager, "call_tool", audited_call_tool)
    setattr(tool_manager, "_qwenpaw_security_center_audit", True)
