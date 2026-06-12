# -*- coding: utf-8 -*-
"""Thin bridge from qwenpaw core into extension/persona_baseline."""
from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path

from ..constant import WORKING_DIR
from ..security.integrity_protection import (
    IntegrityProtectionSettings,
    PersonaBaselineState as NativePersonaBaselineState,
    PersonaDriftAlert as NativePersonaDriftAlert,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXTENSION_DIR = _REPO_ROOT / "extension"
if str(_EXTENSION_DIR) not in sys.path:
    sys.path.insert(0, str(_EXTENSION_DIR))

from persona_baseline.constants import (  # noqa: E402
    CONFIRM_ACCEPT_PHRASE,
    CONFIRM_REESTABLISH_PHRASE,
    CONFIRM_RESTORE_PHRASE,
)
from persona_baseline.guardian import (  # noqa: E402
    PersonaBaselineGuardian as ExtensionPersonaBaselineGuardian,
)
from persona_baseline.guardian import (  # noqa: E402
    PersonaBaselineState as ExtensionPersonaBaselineState,
)
from persona_baseline.guardian import (  # noqa: E402
    PersonaDriftAlert as ExtensionPersonaDriftAlert,
)
from persona_baseline.service import PersonaBaselineService  # noqa: E402
from persona_baseline.sse_hub import PersonaSSEHub  # noqa: E402


def _wire_emitter(service: PersonaBaselineService) -> None:
    from ..app.console_push_store import append as push_append
    from ..app.inbox_store import append_event

    service.emitter.inbox_append = append_event
    service.emitter.push_append = push_append
    service.emitter.sse_publish = service.sse_hub.publish


@lru_cache(maxsize=1)
def get_persona_service(working_dir: Path | None = None) -> PersonaBaselineService:
    root = working_dir or WORKING_DIR
    service = PersonaBaselineService(root)
    _wire_emitter(service)
    return service


def get_integrity_settings_projection() -> IntegrityProtectionSettings:
    base = IntegrityProtectionSettings()
    projection = get_persona_service().get_integrity_projection()
    return IntegrityProtectionSettings(
        persona_protection_enabled=projection["persona_protection_enabled"],
        source_trust_verification_enabled=base.source_trust_verification_enabled,
        health_check_enabled=base.health_check_enabled,
        rule_integrity_check_passive=base.rule_integrity_check_passive,
        protected_paths=tuple(projection["protected_paths"]),
        menus=base.menus,
    )


async def run_startup_scan_if_enabled() -> dict:
    service = get_persona_service()
    if not service.is_enabled():
        return {"skipped": True, "reason": "disabled"}
    return await service.run_startup_scan()


async def notify_file_saved(
    agent_id: str,
    absolute_path: str | Path,
    provenance: str,
) -> None:
    service = get_persona_service()
    if not service.is_enabled():
        return
    await service.coordinator.on_file_saved(
        agent_id=agent_id,
        absolute_path=absolute_path,
        provenance=provenance,
    )


async def stream_persona_events(request) -> AsyncIterator[str]:
    service = get_persona_service()
    if not service.is_enabled():
        yield PersonaSSEHub.format_sse({"type": "disabled"})
        return

    async for event in service.stream_events():
        if await request.is_disconnected():
            break
        yield PersonaSSEHub.format_sse(event)
        await asyncio.sleep(0)


class PersonaBaselineGuardian:
    """Re-export harness API while delegating to extension implementation."""

    def __init__(self, workspace_root: Path, state_dir: Path | None = None) -> None:
        del state_dir
        self._inner = ExtensionPersonaBaselineGuardian(workspace_root)

    def enable(self, protected_paths: tuple[str, ...]) -> NativePersonaBaselineState:
        state = self._inner.enable(protected_paths)
        return _to_native_state(state)

    def scan(self) -> NativePersonaBaselineState:
        return _to_native_state(self._inner.scan())

    def restore(self, relative_path: str) -> bool:
        return self._inner.restore(relative_path)

    def accept(self, relative_path: str) -> bool:
        return self._inner.accept(relative_path)


def _to_native_state(
    state: ExtensionPersonaBaselineState,
) -> NativePersonaBaselineState:
    return NativePersonaBaselineState(
        enabled=state.enabled,
        protected_paths=state.protected_paths,
        alerts=tuple(
            NativePersonaDriftAlert(
                path=alert.path,
                previous_sha256=alert.previous_sha256,
                current_sha256=alert.current_sha256,
                detected_at=alert.detected_at,
            )
            for alert in state.alerts
        ),
        startup_scan_ran=state.startup_scan_ran,
    )


__all__ = [
    "CONFIRM_ACCEPT_PHRASE",
    "CONFIRM_REESTABLISH_PHRASE",
    "CONFIRM_RESTORE_PHRASE",
    "PersonaBaselineGuardian",
    "get_integrity_settings_projection",
    "get_persona_service",
    "notify_file_saved",
    "run_startup_scan_if_enabled",
    "stream_persona_events",
]
