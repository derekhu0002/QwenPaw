# -*- coding: utf-8
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from .paths import workspace_relative_path
from .write_context import is_persona_maintenance

if TYPE_CHECKING:
    from .service import PersonaBaselineService


class PersonaWriteCoordinator:
    def __init__(self, service: "PersonaBaselineService") -> None:
        self._service = service

    async def on_file_saved(
        self,
        *,
        agent_id: str,
        absolute_path: str | Path,
        provenance: str,
        suppress_watch_sec: float = 2.0,
    ) -> None:
        if is_persona_maintenance() or not self._service.is_enabled():
            return
        if provenance == "system_maintenance":
            return

        settings = self._service.settings_store.load()
        workspace = self._service.settings_store.resolve_workspace(agent_id)
        rel_path = workspace_relative_path(workspace, Path(absolute_path))
        if rel_path is None:
            return

        protected = set(self._service.settings_store.effective_paths(settings, agent_id))
        if rel_path not in protected:
            return

        state_dir = self._service.settings_store.agent_state(agent_id)

        if provenance == "operator_console":
            await asyncio.to_thread(
                self._service.adapter.approve_file,
                workspace_root=workspace,
                state_dir=state_dir,
                relative_path=rel_path,
            )
            self._service.drift_store.resolve_for_path(
                agent_id=agent_id,
                path=rel_path,
                status="accepted",
            )
            current_sha = self._file_sha(Path(absolute_path))
            self._service.watch_service.suppress.register(
                agent_id=agent_id,
                path=rel_path,
                sha256=current_sha,
                ttl_seconds=suppress_watch_sec,
            )
            await self._service.emitter.emit_baseline_updated(
                agent_id=agent_id,
                path=rel_path,
                new_sha256=current_sha,
            )
            return

        if provenance in {"agent_tool", "external_untrusted", "external_watch"}:
            provenance_key = (
                "external_watch"
                if provenance in {"external_untrusted", "external_watch"}
                else "agent_tool"
            )
            await self._service._emit_drift_for_path(
                settings,
                agent_id,
                rel_path,
                provenance=provenance_key,
            )

    @staticmethod
    def _file_sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
