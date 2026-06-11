# -*- coding: utf-8 -*-
"""Persistent policy store for credential governance."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ...constant import SECRET_DIR


class CredentialGovernancePolicy(BaseModel):
    """Managed local policy rule for governed credential injection."""

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    enabled: bool = True
    effect: Literal["permit", "deny"] = "permit"
    agent_id: str = ""
    service_id: str = ""
    credential_id: str = ""
    allowed_hosts: list[str] = Field(default_factory=list)
    allowed_mapped_keys: list[str] = Field(default_factory=list)
    cedar_text: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0


class CredentialPolicyStore:
    """JSON-backed policy store.

    Policies live outside the credential store so governance can evolve without
    changing the core credential persistence contract.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (
            SECRET_DIR / "credential_governance" / "policies.json"
        )
        self._lock = threading.RLock()

    def list_policies(self) -> list[CredentialGovernancePolicy]:
        with self._lock:
            return list(self._load().values())

    def matching_policies(
        self,
        *,
        agent_id: str,
        service_id: str,
        credential_id: str,
    ) -> list[CredentialGovernancePolicy]:
        return [
            policy
            for policy in self.list_policies()
            if policy.enabled
            and (not policy.agent_id or policy.agent_id == agent_id)
            and (not policy.service_id or policy.service_id == service_id)
            and (
                not policy.credential_id
                or policy.credential_id == credential_id
            )
        ]

    def create_policy(
        self,
        *,
        name: str,
        enabled: bool = True,
        effect: Literal["permit", "deny"] = "permit",
        agent_id: str = "",
        service_id: str = "",
        credential_id: str = "",
        allowed_hosts: list[str] | None = None,
        allowed_mapped_keys: list[str] | None = None,
        cedar_text: str = "",
    ) -> CredentialGovernancePolicy:
        with self._lock:
            policies = self._load()
            now = time.time()
            policy = CredentialGovernancePolicy(
                id=f"policy_{uuid.uuid4().hex[:12]}",
                name=name.strip(),
                enabled=enabled,
                effect=effect,
                agent_id=agent_id.strip(),
                service_id=service_id.strip(),
                credential_id=credential_id.strip(),
                allowed_hosts=[str(host) for host in (allowed_hosts or []) if str(host)],
                allowed_mapped_keys=[
                    str(key) for key in (allowed_mapped_keys or []) if str(key)
                ],
                cedar_text=cedar_text,
                created_at=now,
                updated_at=now,
            )
            policies[policy.id] = policy
            self._save(policies)
            return policy

    def update_policy(
        self,
        policy_id: str,
        **updates,
    ) -> CredentialGovernancePolicy:
        with self._lock:
            policies = self._load()
            if policy_id not in policies:
                raise ValueError(f"Policy '{policy_id}' not found")
            policy = policies[policy_id]
            data = policy.model_dump()
            for key, value in updates.items():
                if value is not None:
                    data[key] = value
            data["updated_at"] = time.time()
            updated = CredentialGovernancePolicy.model_validate(data)
            policies[policy_id] = updated
            self._save(policies)
            return updated

    def delete_policy(self, policy_id: str) -> bool:
        with self._lock:
            policies = self._load()
            existed = policy_id in policies
            if existed:
                del policies[policy_id]
                self._save(policies)
            return existed

    def _load(self) -> dict[str, CredentialGovernancePolicy]:
        if not self._path.exists():
            return {}
        with open(self._path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        policies: dict[str, CredentialGovernancePolicy] = {}
        for raw in payload.get("policies", []):
            policy = CredentialGovernancePolicy.model_validate(raw)
            policies[policy.id] = policy
        return policies

    def _save(self, policies: dict[str, CredentialGovernancePolicy]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "policies": [policy.model_dump() for policy in policies.values()],
                    "updated_at": time.time(),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )


_POLICY_STORE_SINGLETON: CredentialPolicyStore | None = None


def get_credential_policy_store() -> CredentialPolicyStore:
    global _POLICY_STORE_SINGLETON
    if _POLICY_STORE_SINGLETON is None:
        _POLICY_STORE_SINGLETON = CredentialPolicyStore()
    return _POLICY_STORE_SINGLETON
