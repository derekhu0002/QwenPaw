# -*- coding: utf-8 -*-
"""Tests for credential store and resolver."""

from __future__ import annotations

from pathlib import Path

import pytest

from qwenpaw.config.config import CredentialRef, CredentialScope, CredentialType
from qwenpaw.security.credential_governance.audit import CredentialGovernanceAudit
from qwenpaw.security.credential_governance.gateway import (
    CredentialGovernanceDenied,
    CredentialInjectionGateway,
)
from qwenpaw.security.credential_governance.policy import (
    CredentialPolicyRequest,
    LocalCredentialPolicyEngine,
)
from qwenpaw.security.credential_governance.policy_store import CredentialPolicyStore
from qwenpaw.security.credential_resolver import CredentialResolver
from qwenpaw.security.credential_store import CredentialStore


@pytest.fixture()
def credential_store(tmp_path: Path, monkeypatch):
    import qwenpaw.security.credential_store as store_mod
    import qwenpaw.security.secret_store as secret_mod

    monkeypatch.setattr(store_mod, "SECRET_DIR", tmp_path / "secret")
    monkeypatch.setattr(secret_mod, "_cached_master_key", bytes.fromhex("ab" * 32))
    monkeypatch.setattr(secret_mod, "_cached_fernet", None)
    monkeypatch.setattr(secret_mod, "_get_secret_dir", lambda: tmp_path / "secret")
    return CredentialStore()


def test_create_and_list_agent_credentials(credential_store: CredentialStore):
    created = credential_store.create_credential(
        name="agent token",
        credential_type=CredentialType.TOKEN,
        scope=CredentialScope.AGENT,
        agent_id="alpha",
        data={"token": "abc123"},
    )

    listed = credential_store.list_credentials(
        scope=CredentialScope.AGENT,
        agent_id="alpha",
    )
    assert len(listed) == 1
    assert listed[0]["id"] == created.id
    assert listed[0]["data"]["token"] != "abc123"

    raw = credential_store.get_credential(
        created.id,
        scope=CredentialScope.AGENT,
        agent_id="alpha",
    )
    assert raw is not None
    assert raw.data["token"] == "abc123"


def test_visible_scope_merges_global_and_agent(credential_store: CredentialStore):
    credential_store.create_credential(
        name="global key",
        credential_type=CredentialType.API_KEY,
        scope=CredentialScope.GLOBAL,
        data={"api_key": "global-secret"},
    )
    credential_store.create_credential(
        name="agent key",
        credential_type=CredentialType.API_KEY,
        scope=CredentialScope.AGENT,
        agent_id="alpha",
        data={"api_key": "agent-secret"},
    )

    visible = credential_store.list_visible_credentials("alpha")
    assert len(visible) == 2


def test_resolver_applies_field_map(credential_store: CredentialStore):
    created = credential_store.create_credential(
        name="provider",
        credential_type=CredentialType.API_KEY,
        scope=CredentialScope.AGENT,
        agent_id="alpha",
        data={"api_key": "sk-test"},
    )
    resolver = CredentialResolver()
    resolver._store = credential_store

    mapped = resolver.resolve_mapped(
        CredentialRef(
            credential_id=created.id,
            field_map={"api_key": "header.Authorization"},
        ),
        agent_id="alpha",
    )
    assert mapped["header.Authorization"] == "sk-test"


def test_gateway_falls_back_for_unbound_credentials(
    credential_store: CredentialStore,
    tmp_path: Path,
):
    created = credential_store.create_credential(
        name="legacy mcp token",
        credential_type=CredentialType.TOKEN,
        scope=CredentialScope.AGENT,
        agent_id="alpha",
        data={"token": "legacy-token"},
    )
    resolver = CredentialResolver()
    resolver._store = credential_store
    gateway = CredentialInjectionGateway()
    gateway._store = credential_store
    gateway._resolver = resolver
    gateway._audit = CredentialGovernanceAudit(tmp_path / "audit.jsonl")

    result = gateway.inject_mcp_runtime(
        headers={},
        env={},
        credential_ref=CredentialRef(
            credential_id=created.id,
            field_map={"token": "env.GITHUB_TOKEN"},
        ),
        agent_id="alpha",
        service_id="mcp:github",
    )

    assert result.governed is False
    assert result.decision == "fallback"
    assert result.env["GITHUB_TOKEN"] == "legacy-token"
    events = gateway._audit.read(agent_id="alpha", service_id="mcp:github")
    assert events[0]["decision"] == "fallback"
    assert "legacy-token" not in str(events[0])


def test_gateway_allows_bound_credential(
    credential_store: CredentialStore,
    tmp_path: Path,
):
    created = credential_store.create_credential(
        name="github token",
        credential_type=CredentialType.TOKEN,
        scope=CredentialScope.AGENT,
        agent_id="alpha",
        data={"token": "secret-token"},
        service_id="mcp:github",
        allowed_hosts=["api.github.com"],
        field_map={"token": "header.Authorization"},
    )
    gateway = CredentialInjectionGateway()
    gateway._store = credential_store
    gateway._audit = CredentialGovernanceAudit(tmp_path / "audit.jsonl")

    result = gateway.inject_mcp_runtime(
        headers={},
        env={},
        credential_ref=CredentialRef(
            credential_id=created.id,
            field_map={"token": "header.Authorization"},
        ),
        agent_id="alpha",
        service_id="mcp:github",
        target_url="https://api.github.com/mcp",
    )

    assert result.governed is True
    assert result.headers["Authorization"] == "secret-token"
    events = gateway._audit.read(decision="allow")
    assert events[0]["mapped_keys"] == ["header.Authorization"]
    assert "secret-token" not in str(events[0])


def test_gateway_denies_service_binding_mismatch(
    credential_store: CredentialStore,
    tmp_path: Path,
):
    created = credential_store.create_credential(
        name="github token",
        credential_type=CredentialType.TOKEN,
        scope=CredentialScope.AGENT,
        agent_id="alpha",
        data={"token": "secret-token"},
        service_id="mcp:github",
        allowed_hosts=["api.github.com"],
        field_map={"token": "header.Authorization"},
    )
    gateway = CredentialInjectionGateway()
    gateway._store = credential_store
    gateway._audit = CredentialGovernanceAudit(tmp_path / "audit.jsonl")

    with pytest.raises(CredentialGovernanceDenied, match="service_binding_mismatch"):
        gateway.inject_mcp_runtime(
            headers={},
            env={},
            credential_ref=CredentialRef(
                credential_id=created.id,
                field_map={"token": "header.Authorization"},
            ),
            agent_id="alpha",
            service_id="mcp:slack",
            target_url="https://slack.com/api",
        )


def test_local_policy_engine_rejects_unsupported_target_field(
    credential_store: CredentialStore,
):
    created = credential_store.create_credential(
        name="custom token",
        credential_type=CredentialType.TOKEN,
        scope=CredentialScope.AGENT,
        agent_id="alpha",
        data={"token": "secret-token"},
        service_id="mcp:github",
        field_map={"token": "query.token"},
    )
    decision = LocalCredentialPolicyEngine().authorize(
        request=CredentialPolicyRequest(
            agent_id="alpha",
            request_type="mcp",
            service_id="mcp:github",
            target_host="",
            credential_id=created.id,
            mapped_keys=["query.token"],
        ),
        entry=created,
        credential_ref=CredentialRef(
            credential_id=created.id,
            field_map={"token": "query.token"},
        ),
    )

    assert decision.permit is False
    assert decision.reason == "unsupported_target_field"


def test_policy_store_round_trips_managed_policy(tmp_path: Path):
    store = CredentialPolicyStore(tmp_path / "policies.json")

    created = store.create_policy(
        name="github permit",
        agent_id="alpha",
        service_id="mcp:github",
        credential_id="cred_1",
        allowed_hosts=["api.github.com"],
        allowed_mapped_keys=["header.Authorization"],
    )
    updated = store.update_policy(created.id, enabled=False)

    assert updated.enabled is False
    assert store.list_policies()[0].id == created.id
    assert store.delete_policy(created.id) is True
    assert store.list_policies() == []


def test_local_policy_engine_uses_managed_policy(
    credential_store: CredentialStore,
    tmp_path: Path,
):
    created = credential_store.create_credential(
        name="github token",
        credential_type=CredentialType.TOKEN,
        scope=CredentialScope.AGENT,
        agent_id="alpha",
        data={"token": "secret-token"},
        service_id="mcp:github",
        allowed_hosts=["api.github.com"],
        field_map={"token": "header.Authorization"},
    )
    policy_store = CredentialPolicyStore(tmp_path / "policies.json")
    policy = policy_store.create_policy(
        name="github permit",
        agent_id="alpha",
        service_id="mcp:github",
        credential_id=created.id,
        allowed_hosts=["api.github.com"],
        allowed_mapped_keys=["header.Authorization"],
    )
    engine = LocalCredentialPolicyEngine()
    engine._policy_store = policy_store

    decision = engine.authorize(
        request=CredentialPolicyRequest(
            agent_id="alpha",
            request_type="mcp",
            service_id="mcp:github",
            target_host="api.github.com",
            credential_id=created.id,
            mapped_keys=["header.Authorization"],
        ),
        entry=created,
        credential_ref=CredentialRef(
            credential_id=created.id,
            field_map={"token": "header.Authorization"},
        ),
    )

    assert decision.permit is True
    assert decision.reason == "managed_policy_permit"
    assert decision.policy_id == policy.id

