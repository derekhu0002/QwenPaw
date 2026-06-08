# -*- coding: utf-8 -*-
"""Resolve credential references into runtime parameters."""

from __future__ import annotations

from typing import Any

from ..config.config import CredentialRef, CredentialScope
from .credential_store import get_credential_store


class CredentialResolver:
    """Resolver for runtime credential injection."""

    def __init__(self) -> None:
        self._store = get_credential_store()

    def resolve_ref(
        self,
        credential_ref: CredentialRef | None,
        *,
        agent_id: str | None = None,
    ) -> dict[str, str]:
        if credential_ref is None:
            return {}
        if agent_id:
            entry = self._store.get_visible_credential(
                credential_ref.credential_id,
                agent_id=agent_id,
            )
        else:
            entry = self._store.get_credential(
                credential_ref.credential_id,
                scope=CredentialScope.GLOBAL,
            )
        if entry is None:
            raise ValueError(
                f"Credential '{credential_ref.credential_id}' is not available",
            )
        return dict(entry.data)

    @staticmethod
    def apply_field_map(
        secrets: dict[str, str],
        field_map: dict[str, str] | None,
    ) -> dict[str, str]:
        if not field_map:
            return dict(secrets)
        injected: dict[str, str] = {}
        for source_key, target_key in field_map.items():
            value = secrets.get(source_key)
            if value is None:
                continue
            injected[target_key] = value
        return injected

    def resolve_mapped(
        self,
        credential_ref: CredentialRef | None,
        *,
        agent_id: str | None = None,
    ) -> dict[str, str]:
        if credential_ref is None:
            return {}
        secrets = self.resolve_ref(credential_ref, agent_id=agent_id)
        return self.apply_field_map(secrets, credential_ref.field_map)

    def inject_provider_config(
        self,
        config: dict[str, Any],
        credential_ref: CredentialRef | None,
        *,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        if credential_ref is None:
            return config
        mapped = self.resolve_mapped(credential_ref, agent_id=agent_id)
        result = dict(config)
        if "api_key" in mapped:
            result["api_key"] = mapped["api_key"]
        if "authorization" in mapped:
            headers = dict(result.get("custom_headers") or {})
            headers["Authorization"] = mapped["authorization"]
            result["custom_headers"] = headers
        return result

    def inject_mcp_runtime(
        self,
        *,
        headers: dict[str, str] | None,
        env: dict[str, str] | None,
        credential_ref: CredentialRef | None,
        agent_id: str | None = None,
    ) -> tuple[dict[str, str], dict[str, str]]:
        resolved = self.resolve_mapped(credential_ref, agent_id=agent_id)
        final_headers = dict(headers or {})
        final_env = dict(env or {})
        for key, value in resolved.items():
            if key.startswith("header."):
                final_headers[key.removeprefix("header.")] = value
            elif key.startswith("env."):
                final_env[key.removeprefix("env.")] = value
        return final_headers, final_env


_RESOLVER_SINGLETON: CredentialResolver | None = None


def get_credential_resolver() -> CredentialResolver:
    global _RESOLVER_SINGLETON
    if _RESOLVER_SINGLETON is None:
        _RESOLVER_SINGLETON = CredentialResolver()
    return _RESOLVER_SINGLETON

