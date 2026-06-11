# -*- coding: utf-8 -*-
"""Audit records for governed credential injection decisions."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ...constant import SECRET_DIR


class CredentialGovernanceAudit:
    """Append-only JSONL audit log without credential plaintext."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (SECRET_DIR / "credential_governance" / "audit.jsonl")

    def write(self, event: dict[str, Any]) -> None:
        payload = {
            "timestamp": time.time(),
            **event,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            f.write("\n")

    def read(
        self,
        *,
        limit: int = 100,
        agent_id: str | None = None,
        service_id: str | None = None,
        credential_id: str | None = None,
        decision: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read recent audit events with simple exact-match filters."""

        if not self._path.exists():
            return []

        events: list[dict[str, Any]] = []
        with open(self._path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if agent_id and event.get("agent_id") != agent_id:
                continue
            if service_id and event.get("service_id") != service_id:
                continue
            if credential_id and event.get("credential_id") != credential_id:
                continue
            if decision and event.get("decision") != decision:
                continue
            events.append(event)
            if len(events) >= limit:
                break
        return events


_AUDIT_SINGLETON: CredentialGovernanceAudit | None = None


def get_credential_governance_audit() -> CredentialGovernanceAudit:
    global _AUDIT_SINGLETON
    if _AUDIT_SINGLETON is None:
        _AUDIT_SINGLETON = CredentialGovernanceAudit()
    return _AUDIT_SINGLETON
