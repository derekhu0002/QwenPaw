# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from deploy.api.store import (
    GAP_STATUS_REQUIRED,
    RECOVERY_GATE_OPEN,
    TRUST_STATE_ALIGNED,
    TRUST_STATE_UNTRUSTED,
    SecurityCenterStore,
    _default_client_state,
    derive_shadow_hash,
)


@pytest.fixture
def security_center_store(tmp_path: Path) -> SecurityCenterStore:
    return SecurityCenterStore(tmp_path / "security-center-store.json")


def _run(coroutine):
    return asyncio.run(coroutine)


def _seed_client_state(
    store: SecurityCenterStore,
    *,
    client_id: str,
    requested_at_ns: int,
    overrides: dict[str, object],
) -> None:
    state = store._bootstrap_state()
    client_state = _default_client_state(client_id, requested_at_ns)
    client_state.update(overrides)
    state["clients"][client_id] = client_state
    store._write_locked(state)


@pytest.mark.contract
@pytest.mark.p0
def test_security_center_requires_ttl_driven_untrusted_downgrade(
    security_center_store: SecurityCenterStore,
) -> None:
    """Control point: a previously aligned client remains in the Security Center
    lease registry after its heartbeat expiry moment has already passed.

    Observation point: the cloud-side timeline must expose lease timing fields,
    autonomously downgrade the client to UNTRUSTED, and require recovery
    without relying on a prompt-scripted edge lockdown path.
    """

    client_id = "session_ttl_registry_contract"
    last_heartbeat_at = time.time_ns() - 5_000_000_000
    lease_ttl_seconds = 1
    lease_expires_at = last_heartbeat_at + lease_ttl_seconds * 1_000_000_000

    # // GIVEN
    _seed_client_state(
        security_center_store,
        client_id=client_id,
        requested_at_ns=last_heartbeat_at,
        overrides={
            "trust_state": TRUST_STATE_ALIGNED,
            "recovery_required": False,
            "last_heartbeat_at": last_heartbeat_at,
            "lease_ttl_seconds": lease_ttl_seconds,
            "lease_expires_at": lease_expires_at,
        },
    )

    # // WHEN
    timeline = _run(security_center_store.timeline(client_id))

    # // THEN
    assert timeline is not None
    assert "last_heartbeat_at" in timeline, (
        "Security Center must project the last heartbeat timestamp so the "
        "lease registry can explain why the client expired."
    )
    assert "lease_expires_at" in timeline, (
        "Security Center must project the computed lease expiry time instead "
        "of hiding lease timing inside edge-side prompt logic."
    )
    assert "lease_ttl_seconds" in timeline, (
        "Security Center must project the lease TTL used for active defense."
    )
    assert timeline["trust_state"] == TRUST_STATE_UNTRUSTED, (
        "Security Center must autonomously downgrade an expired client to "
        "UNTRUSTED when the lease TTL has elapsed."
    )
    assert timeline["recovery_required"] is True, (
        "An expired lease must force recovery from the cloud-side lease "
        "monitor before model access is restored."
    )


@pytest.mark.contract
@pytest.mark.p0
def test_security_center_rejects_hash_only_recovery_shortcut(
    security_center_store: SecurityCenterStore,
) -> None:
    """Control point: an UNTRUSTED client attempts recovery with only matching
    hash, sequence, and anchor identifiers, but without a full cloud-validated
    missing-gap proof.

    Observation point: recovery gate closure must be rejected, trust must stay
    non-aligned, and recovery must remain required until the cloud mirror
    accepts a full-chain gap proof.
    """

    client_id = "session_gap_validation_contract"
    requested_at_ns = time.time_ns()
    trusted_anchor_hash = derive_shadow_hash(client_id, "trusted-anchor")
    reported_edge_hash = derive_shadow_hash(client_id, "edge-head")
    stale_shadow_hash = derive_shadow_hash(client_id, "stale-shadow")

    # // GIVEN
    _seed_client_state(
        security_center_store,
        client_id=client_id,
        requested_at_ns=requested_at_ns,
        overrides={
            "shadow_hash": stale_shadow_hash,
            "trust_state": TRUST_STATE_UNTRUSTED,
            "last_trusted_anchor_hash": trusted_anchor_hash,
            "last_trusted_sequence": 10,
            "last_trusted_anchor_event_id": "anchor::10",
            "last_edge_reported_hash": reported_edge_hash,
            "last_edge_reported_sequence": 12,
            "last_edge_reported_anchor_event_id": "anchor::12",
            "gap_status": GAP_STATUS_REQUIRED,
            "recovery_gate_status": RECOVERY_GATE_OPEN,
            "recovery_required": True,
        },
    )

    # // WHEN
    recovery_response = _run(
        security_center_store.recovery_handshake(
            {
                "client_id": client_id,
                "trace_id": f"explicit-gap-verification::{client_id}",
                "local_hash": reported_edge_hash,
                "checkpoint_hash": trusted_anchor_hash,
                "local_sequence": 12,
                "checkpoint_sequence": 10,
                "anchored_event_id": "anchor::12",
                "checkpoint_anchor_id": "anchor::10",
                "requested_at_ns": requested_at_ns,
            },
        ),
    )

    # // THEN
    assert recovery_response["trust_state"] != TRUST_STATE_ALIGNED, (
        "Security Center must not return a client to ALIGNED from the "
        "explicit-gap-verification shortcut when no full-chain gap proof was "
        "validated by the cloud mirror."
    )
    assert recovery_response["recovery_required"] is True, (
        "Recovery must remain required until a full missing-gap proof is "
        "accepted by the cloud-side validator."
    )