# -*- coding: utf-8 -*-
"""Tests for credential store and resolver."""

from __future__ import annotations

from pathlib import Path

import pytest

from qwenpaw.config.config import CredentialRef, CredentialScope, CredentialType
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

