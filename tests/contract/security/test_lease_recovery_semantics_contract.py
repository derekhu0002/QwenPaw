# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest

from tests.integration.conftest import app_server  # noqa: F401

from deploy.api.store import (
    GAP_STATUS_CLEAR,
    GAP_STATUS_REQUIRED,
    RECOVERY_GATE_CLOSED,
    RECOVERY_GATE_OPEN,
    TRUST_STATE_ALIGNED,
    TRUST_STATE_DIVERGED,
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


def _read_security_center_overview(app_server) -> dict[str, object]:
    security_center_api_url = app_server.security_center_api_url
    assert security_center_api_url, (
        "Security Center API must be available for runtime identity projection checks."
    )
    response = app_server.client.get(
        f"{security_center_api_url}/security-center/v1/operator/overview",
        timeout=45.0,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _read_security_center_timeline(app_server, *, client_id: str) -> dict[str, object] | None:
    security_center_api_url = app_server.security_center_api_url
    assert security_center_api_url, (
        "Security Center API must be available for runtime identity projection checks."
    )
    response = app_server.client.get(
        f"{security_center_api_url}/security-center/v1/operator/timelines/{quote(client_id, safe='')}",
        timeout=45.0,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else None


def _submit_console_prompt(
    app_server,
    *,
    user_id: str,
    session_id: str,
    prompt: str,
) -> int:
    payload = {
        "channel": "console",
        "user_id": user_id,
        "session_id": session_id,
        "input": [{"content": [{"type": "text", "text": prompt}]}],
    }
    timeout = httpx.Timeout(45.0, read=5.0)
    with app_server.client.stream(
        "POST",
        f"{app_server.base_url}/api/console/chat",
        json=payload,
        headers={"accept": "text/event-stream"},
        timeout=timeout,
    ) as response:
        _ = "".join(response.iter_text())
        return response.status_code


def _poll_runtime_identity_projection(app_server) -> tuple[dict[str, object], list[str]]:
    deadline = time.time() + 8.0
    last_overview: dict[str, object] = {}
    last_canonical_client_ids: list[str] = []
    while time.time() < deadline:
        overview = _read_security_center_overview(app_server)
        clients = overview.get("clients") if isinstance(overview, dict) else []
        canonical_client_ids = sorted(
            {
                str(client.get("canonical_client_id") or "").strip()
                for client in clients
                if isinstance(client, dict)
                and str(client.get("canonical_client_id") or "").strip()
            },
        )
        last_overview = overview
        last_canonical_client_ids = canonical_client_ids
        if len(canonical_client_ids) > 1:
            return overview, canonical_client_ids
        time.sleep(0.25)
    return last_overview, last_canonical_client_ids


def _read_security_center_store_snapshot(app_server) -> dict[str, object]:
    security_center_data_dir = app_server.security_center_data_dir
    assert security_center_data_dir is not None, (
        "Security Center durable data dir must be exposed by the shared app "
        "fixture so contract tests can inspect the persisted lease registry."
    )
    store_path = security_center_data_dir / "security-center-store.json"
    assert store_path.exists(), (
        "Security Center durable store must exist once the runtime heartbeat "
        "has registered through the cloud-side boundary."
    )
    payload = json.loads(store_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _poll_projected_lease_client(app_server) -> tuple[dict[str, object], dict[str, object]]:
    deadline = time.time() + 15.0
    last_overview: dict[str, object] = {}
    last_client: dict[str, object] = {}
    while time.time() < deadline:
        overview = _read_security_center_overview(app_server)
        clients = overview.get("clients") if isinstance(overview, dict) else []
        if isinstance(clients, list):
            for client in clients:
                if not isinstance(client, dict):
                    continue
                if (
                    str(client.get("canonical_client_id") or "").strip()
                    and int(client.get("last_heartbeat_at") or 0) > 0
                    and int(client.get("lease_expires_at") or 0) > 0
                    and int(client.get("lease_ttl_seconds") or 0) > 0
                ):
                    return overview, client
        last_overview = overview
        last_client = clients[-1] if isinstance(clients, list) and clients else {}
        time.sleep(0.25)
    return last_overview, last_client


def _poll_ttl_expired_timeline(app_server, *, client_id: str) -> dict[str, object] | None:
    deadline = time.time() + 15.0
    last_timeline: dict[str, object] | None = None
    while time.time() < deadline:
        timeline = _read_security_center_timeline(app_server, client_id=client_id)
        if isinstance(timeline, dict):
            last_timeline = timeline
            if (
                timeline.get("trust_state") == TRUST_STATE_UNTRUSTED
                and timeline.get("divergence_reason") == "lease_ttl_expired"
                and timeline.get("recovery_required") is True
            ):
                return timeline
        time.sleep(0.25)
    return last_timeline


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


@pytest.mark.contract
@pytest.mark.p0
def test_runtime_startup_registers_lease_heartbeat_without_prompt(app_server) -> None:
    """Control point: start a real QwenPaw runtime and observe Security Center
    before any user prompt mentions lease warmup or lease expiry.

    Observation point: Security Center must already show at least one client
    lease registration with nonzero last_heartbeat_at and lease_expires_at so
    active defense does not depend on prompt-scripted warmup wording.
    """

    if app_server.startup_error is not None:
        raise AssertionError(app_server.startup_error)

    # // GIVEN
    security_center_api_url = app_server.security_center_api_url
    assert security_center_api_url, (
        "Security Center API must be available so startup lease registration "
        "can be observed through the cloud-side boundary."
    )

    # // WHEN
    overview_response = app_server.client.get(
        f"{security_center_api_url}/security-center/v1/operator/overview",
        timeout=45.0,
    )
    overview_response.raise_for_status()
    overview = overview_response.json()
    clients = overview.get("clients") if isinstance(overview, dict) else []

    # // THEN
    assert isinstance(clients, list) and clients, (
        "Security Center must register a lease client automatically at runtime "
        "startup; registration must not wait for a user warmup prompt."
    )
    assert any(
        int(client.get("last_heartbeat_at") or 0) > 0
        and int(client.get("lease_expires_at") or 0) > 0
        and int(client.get("lease_ttl_seconds") or 0) > 0
        for client in clients
        if isinstance(client, dict)
    ), (
        "Security Center must project nonzero last_heartbeat_at, "
        "lease_expires_at, and lease_ttl_seconds for a startup-registered "
        "client before any user prompt drives the lease flow."
    )


@pytest.mark.contract
@pytest.mark.p0
def test_security_center_projects_fresh_runtime_startup_as_aligned_clear_terminal(
    app_server,
) -> None:
    """Control point: start a real QwenPaw runtime from a fresh app_server
    bootstrap and observe Security Center before any intentional runtime stop,
    offline lease-expiry demonstration, or session-scoped recovery workflow.

    Observation point: Security Center must project exactly one canonical
    runtime terminal with nonzero durable lease fields, trust_state ALIGNED,
    gap_status CLEAR, recovery_gate_status CLEAR, recovery_required=false,
    and no missing_gap_proof or other recovery-gated startup state.
    """

    if app_server.startup_error is not None:
        raise AssertionError(app_server.startup_error)

    # // GIVEN
    projected_overview, projected_client = _poll_projected_lease_client(app_server)
    canonical_client_id = str(projected_client.get("canonical_client_id") or "").strip()
    assert canonical_client_id, (
        "Security Center must project one canonical runtime client with "
        "nonzero durable lease timing before startup normal-admission can be "
        f"validated; observed overview={projected_overview!r}."
    )
    overview_clients = projected_overview.get("clients") if isinstance(projected_overview, dict) else []
    canonical_client_ids = sorted(
        {
            str(client.get("canonical_client_id") or "").strip()
            for client in overview_clients
            if isinstance(client, dict)
            and str(client.get("canonical_client_id") or "").strip()
        },
    )
    durable_store = _read_security_center_store_snapshot(app_server)
    durable_clients = durable_store.get("clients") if isinstance(durable_store, dict) else {}
    durable_client = durable_clients.get(canonical_client_id, {}) if isinstance(durable_clients, dict) else {}

    # // WHEN
    startup_timeline = _read_security_center_timeline(
        app_server,
        client_id=canonical_client_id,
    )

    # // THEN
    assert len(canonical_client_ids) == 1, (
        "Startup_Admission_Gap: a fresh online runtime must project as one "
        "canonical Security Center terminal before any lease-expiry or recovery "
        f"workflow begins; observed canonical terminals={canonical_client_ids!r} from overview={projected_overview!r}."
    )
    assert int(durable_client.get("last_heartbeat_at") or 0) > 0, (
        "Startup_Admission_Gap: the canonical startup terminal must already "
        "persist last_heartbeat_at in the durable Security Center store."
    )
    assert int(durable_client.get("lease_expires_at") or 0) > 0, (
        "Startup_Admission_Gap: the canonical startup terminal must already "
        "persist lease_expires_at in the durable Security Center store."
    )
    assert projected_client.get("trust_state") == TRUST_STATE_ALIGNED, (
        "Startup_Admission_Gap: a fresh online runtime must start as ALIGNED, "
        "not as a recovery-gated terminal. "
        f"Observed overview client={projected_client!r}."
    )
    assert projected_client.get("gap_status") == GAP_STATUS_CLEAR, (
        "Startup_Admission_Gap: a fresh online runtime must not open a missing "
        f"gap on startup. Observed overview client={projected_client!r}."
    )
    assert projected_client.get("recovery_gate_status") == RECOVERY_GATE_CLOSED, (
        "Startup_Admission_Gap: startup heartbeat must not be treated as a "
        f"recovery-gated missing-gap attempt. Observed overview client={projected_client!r}."
    )
    assert projected_client.get("recovery_required") is False, (
        "Startup_Admission_Gap: a normally online startup terminal must not "
        "require recovery before any offline lease-expiry event has occurred."
    )
    assert (projected_client.get("divergence_reason") or "") == "", (
        "Startup_Admission_Gap: a fresh online startup terminal must not be "
        f"tagged with a startup divergence reason. Observed overview client={projected_client!r}."
    )
    assert isinstance(startup_timeline, dict), (
        "Security Center must expose the canonical startup terminal timeline "
        "through the cloud-side boundary."
    )
    assert startup_timeline.get("trust_state") == TRUST_STATE_ALIGNED, (
        "Startup_Admission_Gap: the canonical startup timeline must be ALIGNED "
        f"before any offline lease expiry occurs. Observed timeline={startup_timeline!r}."
    )
    assert startup_timeline.get("gap_status") == GAP_STATUS_CLEAR, (
        "Startup_Admission_Gap: the canonical startup timeline must remain CLEAR "
        f"before any missing-gap recovery workflow is triggered. Observed timeline={startup_timeline!r}."
    )
    assert startup_timeline.get("recovery_gate_status") == RECOVERY_GATE_CLOSED, (
        "Startup_Admission_Gap: the canonical startup timeline must not open a "
        f"recovery gate on fresh startup. Observed timeline={startup_timeline!r}."
    )
    assert startup_timeline.get("recovery_required") is False, (
        "Startup_Admission_Gap: a fresh online runtime must not require recovery "
        f"at startup. Observed timeline={startup_timeline!r}."
    )
    assert (startup_timeline.get("divergence_reason") or "") == "", (
        "Startup_Admission_Gap: a fresh online startup timeline must not be "
        f"tagged with missing_gap_proof or any other divergence reason. Observed timeline={startup_timeline!r}."
    )


@pytest.mark.contract
@pytest.mark.p0
def test_security_center_projects_one_online_runtime_as_one_canonical_terminal(
    app_server,
) -> None:
    """Control point: start a real QwenPaw runtime, let startup heartbeat
    register automatically, then drive one session-scoped lease warmup through
    the live console without forking the runtime.

    Observation point: Security Center must still project exactly one canonical
    terminal for that online runtime, and no projected terminal may show a
    false local-hash DIVERGED/OPEN recovery gate when no fork point exists.
    """

    if app_server.startup_error is not None:
        raise AssertionError(app_server.startup_error)

    session_id = "security-center-online-runtime-identity-contract"

    # // GIVEN
    baseline_overview = _read_security_center_overview(app_server)
    baseline_clients = baseline_overview.get("clients") if isinstance(baseline_overview, dict) else []
    assert isinstance(baseline_clients, list) and baseline_clients, (
        "Runtime startup must already project one lease-bearing Security Center "
        "client before the session-scoped flow is exercised."
    )

    # // WHEN
    console_status = _submit_console_prompt(
        app_server,
        user_id="security_contract_operator",
        session_id=session_id,
        prompt=(
            "Warm the runtime for lease heartbeat monitoring before the "
            "Security Center lease window expires."
        ),
    )
    overview_after_session, canonical_client_ids = _poll_runtime_identity_projection(app_server)

    # // THEN
    assert console_status == 200, (
        "The live console control point must complete so the contract can "
        "observe post-session Security Center identity projection."
    )
    assert len(canonical_client_ids) == 1, (
        "One live online runtime must converge to one canonical Security "
        "Center terminal after startup heartbeat and later session activity; "
        f"observed canonical terminals={canonical_client_ids!r} from overview={overview_after_session!r}."
    )

    false_diverged_timelines: list[dict[str, object]] = []
    for canonical_client_id in canonical_client_ids:
        timeline = _read_security_center_timeline(
            app_server,
            client_id=canonical_client_id,
        )
        if not isinstance(timeline, dict):
            continue
        if (
            timeline.get("trust_state") == TRUST_STATE_DIVERGED
            and timeline.get("recovery_gate_status") == RECOVERY_GATE_OPEN
            and timeline.get("divergence_reason") == "local_hash_mismatch"
            and timeline.get("fork_point") in (None, {}, [])
        ):
            false_diverged_timelines.append(timeline)

    assert not false_diverged_timelines, (
        "A live online runtime with no fork point must not be projected as a "
        "false local-hash DIVERGED/OPEN recovery gate in Security Center; "
        f"observed false divergence timelines={false_diverged_timelines!r}."
    )


@pytest.mark.contract
@pytest.mark.p0
def test_security_center_persists_runtime_lease_fields_and_downgrades_after_stop(
    app_server,
) -> None:
    """Control point: start a real QwenPaw runtime, observe a projected
    lease-bearing canonical client, inspect the durable Security Center store,
    then stop the runtime and wait for the same canonical client to miss the
    TTL window.

    Observation point: the durable store must already persist nonzero
    last_heartbeat_at, lease_ttl_seconds, and lease_expires_at for that same
    canonical client before the stop, and overview/timeline must later expose
    UNTRUSTED with divergence_reason=lease_ttl_expired after heartbeat loss.
    """

    if app_server.startup_error is not None:
        raise AssertionError(app_server.startup_error)

    # // GIVEN
    projected_overview, projected_client = _poll_projected_lease_client(app_server)
    canonical_client_id = str(projected_client.get("canonical_client_id") or "").strip()
    assert canonical_client_id, (
        "Security Center must project one canonical runtime client with "
        "nonzero lease timing before durable lease persistence can be "
        f"validated; observed overview={projected_overview!r}."
    )

    durable_store = _read_security_center_store_snapshot(app_server)
    durable_clients = durable_store.get("clients") if isinstance(durable_store, dict) else {}
    durable_client = durable_clients.get(canonical_client_id, {}) if isinstance(durable_clients, dict) else {}

    # // WHEN
    assert int(durable_client.get("last_heartbeat_at") or 0) > 0, (
        "Lease_Persistence_Gap: Security Center overview can already project a "
        "lease-bearing canonical runtime client, but the durable store still "
        "persists last_heartbeat_at=0 for that client."
    )
    assert int(durable_client.get("lease_ttl_seconds") or 0) > 0, (
        "Lease_Persistence_Gap: Security Center must durably persist "
        "lease_ttl_seconds for the canonical runtime client instead of keeping "
        "TTL only in read-model projection."
    )
    assert int(durable_client.get("lease_expires_at") or 0) > 0, (
        "Lease_Persistence_Gap: Security Center overview can project lease "
        "expiry, but the durable store still persists lease_expires_at=0 for "
        "the canonical runtime client."
    )

    if app_server.process.poll() is None:
        app_server.process.terminate()
        app_server.process.wait(timeout=15)
    expired_timeline = _poll_ttl_expired_timeline(
        app_server,
        client_id=canonical_client_id,
    )
    expired_overview = _read_security_center_overview(app_server)

    # // THEN
    assert isinstance(expired_timeline, dict), (
        "Security Center must keep exposing the canonical runtime timeline "
        "after runtime stop so TTL expiry can be observed through the cloud-side boundary."
    )
    assert expired_timeline.get("trust_state") == TRUST_STATE_UNTRUSTED, (
        "Lease_Persistence_Gap: after runtime stop and TTL expiry, Security "
        "Center must downgrade the canonical runtime client to UNTRUSTED. "
        f"Observed timeline={expired_timeline!r}."
    )
    assert expired_timeline.get("divergence_reason") == "lease_ttl_expired", (
        "Lease_Persistence_Gap: runtime stop must surface through the canonical "
        "client as divergence_reason=lease_ttl_expired, not as an ALIGNED or "
        f"projection-only state. Observed timeline={expired_timeline!r}."
    )
    assert expired_timeline.get("recovery_required") is True, (
        "Lease_Persistence_Gap: an expired runtime lease must reopen recovery "
        "before model access is restored."
    )
    overview_clients = expired_overview.get("clients") if isinstance(expired_overview, dict) else []
    matching_clients = [
        client
        for client in overview_clients
        if isinstance(client, dict)
        and str(client.get("canonical_client_id") or "").strip() == canonical_client_id
    ]
    assert any(
        client.get("trust_state") == TRUST_STATE_UNTRUSTED
        and client.get("divergence_reason") == "lease_ttl_expired"
        for client in matching_clients
    ), (
        "Lease_Persistence_Gap: operator overview must expose the same stopped "
        "canonical runtime client as UNTRUSTED with lease_ttl_expired after TTL loss; "
        f"observed overview={expired_overview!r}."
    )