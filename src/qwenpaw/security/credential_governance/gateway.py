# -*- coding: utf-8 -*-
"""Runtime gateway for governed credential injection.

The gateway is a thin opt-in layer. Credentials without governance metadata
continue through the legacy resolver path unless strict mode is enabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from ...config.config import CredentialEntry, CredentialRef, CredentialScope
from ...constant import EnvVarLoader
from ..credential_resolver import get_credential_resolver
from ..credential_store import get_credential_store
from .audit import get_credential_governance_audit
from .policy import CredentialPolicyRequest, get_credential_policy_engine


class CredentialGovernanceDenied(RuntimeError):
    """Raised when strict governance denies a credential injection."""


@dataclass(frozen=True)
class InjectionResult:
    headers: dict[str, str]
    env: dict[str, str]
    governed: bool
    decision: str
    reason: str


def _target_host(target_url: str | None) -> str:
    if not target_url:
        return ""
    return urlparse(target_url).hostname or ""


class CredentialInjectionGateway:
    """Authorize and perform governed credential injection."""

    def __init__(self) -> None:
        self._store = get_credential_store()
        self._resolver = get_credential_resolver()
        self._audit = get_credential_governance_audit()
        self._policy_engine = get_credential_policy_engine()

    @staticmethod
    def _is_strict_mode() -> bool:
        return EnvVarLoader.get_bool(
            "QWENPAW_CREDENTIAL_GOVERNANCE_STRICT",
            False,
        )

    @staticmethod
    def _entry_is_bound(entry: CredentialEntry) -> bool:
        return bool(entry.service_id or entry.allowed_hosts or entry.field_map)

    @staticmethod
    def _mapped_fields(
        entry: CredentialEntry,
        credential_ref: CredentialRef,
    ) -> dict[str, str]:
        return entry.field_map or credential_ref.field_map

    @staticmethod
    def _inject_mapped(
        *,
        headers: dict[str, str],
        env: dict[str, str],
        secrets: dict[str, str],
        field_map: dict[str, str],
    ) -> tuple[dict[str, str], dict[str, str], list[str]]:
        final_headers = dict(headers)
        final_env = dict(env)
        injected_keys: list[str] = []

        for source_key, target_key in field_map.items():
            value = secrets.get(source_key)
            if value is None:
                continue
            if target_key.startswith("header."):
                final_headers[target_key.removeprefix("header.")] = value
                injected_keys.append(target_key)
            elif target_key.startswith("env."):
                final_env[target_key.removeprefix("env.")] = value
                injected_keys.append(target_key)

        return final_headers, final_env, injected_keys

    def inject_mcp_runtime(
        self,
        *,
        headers: dict[str, str] | None,
        env: dict[str, str] | None,
        credential_ref: CredentialRef | None,
        agent_id: str | None,
        service_id: str,
        target_url: str | None = None,
    ) -> InjectionResult:
        """Authorize and inject credentials for an MCP service."""

        base_headers = dict(headers or {})
        base_env = dict(env or {})
        if credential_ref is None:
            return InjectionResult(
                headers=base_headers,
                env=base_env,
                governed=False,
                decision="skip",
                reason="no_credential_ref",
            )

        entry = (
            self._store.get_visible_credential(
                credential_ref.credential_id,
                agent_id=agent_id,
            )
            if agent_id
            else self._store.get_credential(
                credential_ref.credential_id,
                scope=CredentialScope.GLOBAL,
            )
        )

        if entry is None:
            return self._legacy_or_deny(
                headers=base_headers,
                env=base_env,
                credential_ref=credential_ref,
                agent_id=agent_id,
                service_id=service_id,
                reason="credential_not_found",
            )

        if not self._entry_is_bound(entry):
            return self._legacy_or_deny(
                headers=base_headers,
                env=base_env,
                credential_ref=credential_ref,
                agent_id=agent_id,
                service_id=service_id,
                reason="unbound_credential",
            )

        host = _target_host(target_url)
        field_map = self._mapped_fields(entry, credential_ref)
        policy_request = CredentialPolicyRequest(
            agent_id=agent_id or "",
            request_type="mcp",
            service_id=service_id,
            target_host=host,
            credential_id=credential_ref.credential_id,
            mapped_keys=list(field_map.values()),
        )
        policy_decision = self._policy_engine.authorize(
            request=policy_request,
            entry=entry,
            credential_ref=credential_ref,
        )
        if not policy_decision.permit:
            self._audit_decision(
                agent_id=agent_id,
                service_id=service_id,
                credential_id=credential_ref.credential_id,
                target_host=host,
                decision="deny",
                reason=policy_decision.reason,
                mapped_keys=[],
                policy_id=policy_decision.policy_id,
            )
            raise CredentialGovernanceDenied(policy_decision.reason)

        approved_keys = set(policy_decision.approved_mapped_keys or field_map.values())
        approved_field_map = {
            source: target
            for source, target in field_map.items()
            if target in approved_keys
        }
        next_headers, next_env, injected_keys = self._inject_mapped(
            headers=base_headers,
            env=base_env,
            secrets=entry.data,
            field_map=approved_field_map,
        )
        self._audit_decision(
            agent_id=agent_id,
            service_id=service_id,
            credential_id=credential_ref.credential_id,
            target_host=host,
            decision="allow",
            reason=policy_decision.reason,
            mapped_keys=injected_keys,
            policy_id=policy_decision.policy_id,
        )
        return InjectionResult(
            headers=next_headers,
            env=next_env,
            governed=True,
            decision="allow",
            reason=policy_decision.reason,
        )

    def _legacy_or_deny(
        self,
        *,
        headers: dict[str, str],
        env: dict[str, str],
        credential_ref: CredentialRef,
        agent_id: str | None,
        service_id: str,
        reason: str,
    ) -> InjectionResult:
        if self._is_strict_mode():
            self._audit_decision(
                agent_id=agent_id,
                service_id=service_id,
                credential_id=credential_ref.credential_id,
                target_host="",
                decision="deny",
                reason=reason,
                mapped_keys=[],
            )
            raise CredentialGovernanceDenied(reason)

        next_headers, next_env = self._resolver.inject_mcp_runtime(
            headers=headers,
            env=env,
            credential_ref=credential_ref,
            agent_id=agent_id,
        )
        self._audit_decision(
            agent_id=agent_id,
            service_id=service_id,
            credential_id=credential_ref.credential_id,
            target_host="",
            decision="fallback",
            reason=reason,
            mapped_keys=[],
            policy_id="legacy-compatibility",
        )
        return InjectionResult(
            headers=next_headers,
            env=next_env,
            governed=False,
            decision="fallback",
            reason=reason,
        )

    def _audit_decision(
        self,
        *,
        agent_id: str | None,
        service_id: str,
        credential_id: str,
        target_host: str,
        decision: str,
        reason: str,
        mapped_keys: list[str],
        policy_id: str = "",
    ) -> None:
        self._audit.write(
            {
                "agent_id": agent_id or "",
                "request_type": "mcp",
                "service_id": service_id,
                "credential_id": credential_id,
                "target_host": target_host,
                "decision": decision,
                "decision_source": "local",
                "policy_id": policy_id,
                "reason_code": reason,
                "mapped_keys": mapped_keys,
            },
        )


_GATEWAY_SINGLETON: CredentialInjectionGateway | None = None


def get_credential_injection_gateway() -> CredentialInjectionGateway:
    global _GATEWAY_SINGLETON
    if _GATEWAY_SINGLETON is None:
        _GATEWAY_SINGLETON = CredentialInjectionGateway()
    return _GATEWAY_SINGLETON
