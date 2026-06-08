# -*- coding: utf-8 -*-
"""Credential storage with scope isolation and encrypted persistence."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from ..config.config import (
    CredentialEntry,
    CredentialScope,
    CredentialType,
)
from ..constant import SECRET_DIR
from .secret_store import decrypt, encrypt, is_encrypted


def _mask_secret_value(value: str) -> str:
    if not value:
        return value
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 6)}{value[-4:]}"


class CredentialStore:
    """Persistent store for global and per-agent credentials."""

    def __init__(self) -> None:
        self._root = SECRET_DIR / "credentials"
        self._global_path = self._root / "global.json"
        self._agents_dir = self._root / "agents"
        self._lock = threading.RLock()
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._agents_dir.mkdir(parents=True, exist_ok=True)
        for path in (self._root, self._agents_dir):
            try:
                os.chmod(path, 0o700)
            except OSError:
                pass

    def _scope_path(
        self,
        scope: CredentialScope,
        agent_id: str | None,
    ) -> Path:
        if scope == CredentialScope.GLOBAL:
            return self._global_path
        if not agent_id:
            raise ValueError("agent_id is required for agent-scoped credentials")
        return self._agents_dir / f"{agent_id}.json"

    @staticmethod
    def _serialize_entry(entry: CredentialEntry) -> dict[str, Any]:
        payload = entry.model_dump()
        payload["data"] = {
            k: encrypt(v) if isinstance(v, str) and v and not is_encrypted(v) else v
            for k, v in payload.get("data", {}).items()
        }
        return payload

    @staticmethod
    def _deserialize_entry(payload: dict[str, Any]) -> CredentialEntry:
        raw = dict(payload)
        raw_data = raw.get("data", {}) or {}
        raw["data"] = {
            str(k): decrypt(v) if isinstance(v, str) else str(v)
            for k, v in raw_data.items()
        }
        return CredentialEntry.model_validate(raw)

    @staticmethod
    def _to_public(entry: CredentialEntry) -> dict[str, Any]:
        payload = entry.model_dump()
        payload["data"] = {
            key: _mask_secret_value(value) if isinstance(value, str) else value
            for key, value in entry.data.items()
        }
        return payload

    def _load_scope_entries(
        self,
        scope: CredentialScope,
        agent_id: str | None,
    ) -> dict[str, CredentialEntry]:
        path = self._scope_path(scope, agent_id)
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        entries: dict[str, CredentialEntry] = {}
        for raw in payload.get("entries", []):
            entry = self._deserialize_entry(raw)
            entries[entry.id] = entry
        return entries

    def _save_scope_entries(
        self,
        scope: CredentialScope,
        agent_id: str | None,
        entries: dict[str, CredentialEntry],
    ) -> None:
        path = self._scope_path(scope, agent_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "entries": [self._serialize_entry(it) for it in entries.values()],
            "updated_at": time.time(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def list_credentials(
        self,
        *,
        scope: CredentialScope,
        agent_id: str | None = None,
        include_secret_data: bool = False,
    ) -> list[dict[str, Any] | CredentialEntry]:
        with self._lock:
            entries = self._load_scope_entries(scope, agent_id)
        values = list(entries.values())
        if include_secret_data:
            return values
        return [self._to_public(it) for it in values]

    def list_visible_credentials(self, agent_id: str) -> list[dict[str, Any]]:
        with self._lock:
            merged: dict[str, CredentialEntry] = {}
            for entry in self._load_scope_entries(
                CredentialScope.GLOBAL,
                None,
            ).values():
                merged[entry.id] = entry
            for entry in self._load_scope_entries(
                CredentialScope.AGENT,
                agent_id,
            ).values():
                merged[entry.id] = entry
            return [self._to_public(it) for it in merged.values()]

    def get_credential(
        self,
        credential_id: str,
        *,
        scope: CredentialScope,
        agent_id: str | None = None,
    ) -> CredentialEntry | None:
        with self._lock:
            entries = self._load_scope_entries(scope, agent_id)
            return entries.get(credential_id)

    def get_visible_credential(
        self,
        credential_id: str,
        *,
        agent_id: str,
    ) -> CredentialEntry | None:
        with self._lock:
            agent_entries = self._load_scope_entries(
                CredentialScope.AGENT,
                agent_id,
            )
            if credential_id in agent_entries:
                return agent_entries[credential_id]
            global_entries = self._load_scope_entries(CredentialScope.GLOBAL, None)
            return global_entries.get(credential_id)

    def create_credential(
        self,
        *,
        name: str,
        credential_type: CredentialType,
        scope: CredentialScope,
        data: dict[str, str],
        agent_id: str | None = None,
        description: str = "",
    ) -> CredentialEntry:
        with self._lock:
            entries = self._load_scope_entries(scope, agent_id)
            credential_id = f"cred_{uuid.uuid4().hex[:12]}"
            now = time.time()
            entry = CredentialEntry(
                id=credential_id,
                name=name.strip(),
                type=credential_type,
                scope=scope,
                agent_id=agent_id or "",
                description=description,
                data={str(k): str(v) for k, v in data.items()},
                created_at=now,
                updated_at=now,
            )
            entries[entry.id] = entry
            self._save_scope_entries(scope, agent_id, entries)
            return entry

    def update_credential(
        self,
        credential_id: str,
        *,
        scope: CredentialScope,
        agent_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        data: dict[str, str] | None = None,
        credential_type: CredentialType | None = None,
    ) -> CredentialEntry:
        with self._lock:
            entries = self._load_scope_entries(scope, agent_id)
            if credential_id not in entries:
                raise ValueError(f"Credential '{credential_id}' not found")
            entry = entries[credential_id]
            if name is not None:
                entry.name = name.strip()
            if description is not None:
                entry.description = description
            if credential_type is not None:
                entry.type = credential_type
            if data is not None:
                entry.data = {str(k): str(v) for k, v in data.items()}
            entry.updated_at = time.time()
            entries[credential_id] = entry
            self._save_scope_entries(scope, agent_id, entries)
            return entry

    def delete_credential(
        self,
        credential_id: str,
        *,
        scope: CredentialScope,
        agent_id: str | None = None,
    ) -> bool:
        with self._lock:
            entries = self._load_scope_entries(scope, agent_id)
            existed = credential_id in entries
            if existed:
                del entries[credential_id]
                self._save_scope_entries(scope, agent_id, entries)
            return existed


_STORE_SINGLETON: CredentialStore | None = None
_STORE_SINGLETON_LOCK = threading.Lock()


def get_credential_store() -> CredentialStore:
    global _STORE_SINGLETON
    if _STORE_SINGLETON is not None:
        return _STORE_SINGLETON
    with _STORE_SINGLETON_LOCK:
        if _STORE_SINGLETON is None:
            _STORE_SINGLETON = CredentialStore()
    return _STORE_SINGLETON

