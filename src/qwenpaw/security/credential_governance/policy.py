# -*- coding: utf-8 -*-
"""Policy engine interface for credential governance.

The first implementation is local and deterministic. Cedar can be added later
behind the same ``CredentialPolicyEngine`` interface without changing MCP or
credential storage code.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...config.config import CredentialEntry, CredentialRef
from .policy_store import get_credential_policy_store


@dataclass(frozen=True)
class CredentialPolicyRequest:
    """Trusted context for a candidate credential injection."""

    agent_id: str
    request_type: str
    service_id: str
    target_host: str
    credential_id: str
    mapped_keys: list[str]


@dataclass(frozen=True)
class CredentialPolicyDecision:
    """Authorization result from a credential policy engine."""

    permit: bool
    reason: str
    policy_id: str = "local-default"
    approved_mapped_keys: tuple[str, ...] = ()


class CredentialPolicyEngine:
    """Interface for credential injection authorization."""

    def authorize(
        self,
        *,
        request: CredentialPolicyRequest,
        entry: CredentialEntry,
        credential_ref: CredentialRef,
    ) -> CredentialPolicyDecision:
        raise NotImplementedError


class LocalCredentialPolicyEngine(CredentialPolicyEngine):
    """Local fail-closed policy for governed credentials."""

    def __init__(self) -> None:
        self._policy_store = get_credential_policy_store()

    def authorize(
        self,
        *,
        request: CredentialPolicyRequest,
        entry: CredentialEntry,
        credential_ref: CredentialRef,
    ) -> CredentialPolicyDecision:
        managed_decision = self._authorize_from_managed_policies(
            request=request,
        )
        if managed_decision is not None:
            return managed_decision

        if entry.service_id and entry.service_id != request.service_id:
            return CredentialPolicyDecision(False, "service_binding_mismatch")

        if (
            entry.allowed_hosts
            and request.target_host
            and request.target_host not in entry.allowed_hosts
        ):
            return CredentialPolicyDecision(False, "host_not_allowed")

        field_map = entry.field_map or credential_ref.field_map
        if not field_map:
            return CredentialPolicyDecision(False, "empty_field_map")

        mapped_keys = list(field_map.values())
        if any(
            not (target.startswith("header.") or target.startswith("env."))
            for target in mapped_keys
        ):
            return CredentialPolicyDecision(False, "unsupported_target_field")

        return CredentialPolicyDecision(
            True,
            "local_policy_permit",
            approved_mapped_keys=tuple(mapped_keys),
        )

    def _authorize_from_managed_policies(
        self,
        *,
        request: CredentialPolicyRequest,
    ) -> CredentialPolicyDecision | None:
        policies = self._policy_store.matching_policies(
            agent_id=request.agent_id,
            service_id=request.service_id,
            credential_id=request.credential_id,
        )
        if not policies:
            return None

        for policy in policies:
            if policy.effect == "deny":
                return CredentialPolicyDecision(
                    False,
                    "managed_policy_deny",
                    policy_id=policy.id,
                )

            if (
                policy.allowed_hosts
                and request.target_host
                and request.target_host not in policy.allowed_hosts
            ):
                return CredentialPolicyDecision(
                    False,
                    "managed_policy_host_not_allowed",
                    policy_id=policy.id,
                )

            approved_keys = (
                policy.allowed_mapped_keys
                if policy.allowed_mapped_keys
                else request.mapped_keys
            )
            if not approved_keys:
                return CredentialPolicyDecision(
                    False,
                    "managed_policy_empty_mapped_keys",
                    policy_id=policy.id,
                )

            return CredentialPolicyDecision(
                True,
                "managed_policy_permit",
                policy_id=policy.id,
                approved_mapped_keys=tuple(approved_keys),
            )

        return None


_POLICY_ENGINE_SINGLETON: CredentialPolicyEngine | None = None


def get_credential_policy_engine() -> CredentialPolicyEngine:
    global _POLICY_ENGINE_SINGLETON
    if _POLICY_ENGINE_SINGLETON is None:
        _POLICY_ENGINE_SINGLETON = LocalCredentialPolicyEngine()
    return _POLICY_ENGINE_SINGLETON
