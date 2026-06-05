from __future__ import annotations

import hashlib
import json
import os
import time

from fastapi.testclient import TestClient

from deploy.api.app import create_app
from deploy.api.store import SecurityCenterStore, derive_shadow_hash


def _canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def test_security_center_store_uses_configured_data_dir(tmp_path, monkeypatch) -> None:
    """Control point: configure QWENPAW_SECURITY_CENTER_DATA_DIR before creating the default store.

    Observation point: deploy/api must place its durable store inside the configured
    directory instead of silently reusing the repository-local data path.
    """

    monkeypatch.setenv("QWENPAW_SECURITY_CENTER_DATA_DIR", str(tmp_path))
    store = SecurityCenterStore.from_default()

    assert store._path == tmp_path / "security-center-store.json"

    monkeypatch.delenv("QWENPAW_SECURITY_CENTER_DATA_DIR", raising=False)


def _build_confirmation_anchor(*, run_id: str, session_id: str, user_id: str, tool_name: str, prior_hash: str, sequence: int, anchored_event_id: str, confirmed_at: float) -> dict:
    confirmation_digest = hashlib.sha256(
        "|".join(
            (
                user_id,
                "console",
                session_id,
                "approval-agent",
                "",
                tool_name,
                "approve payroll export",
            ),
        ).encode("utf-8"),
    ).hexdigest()
    chain_material = {
        "prior_hash": prior_hash,
        "confirmation_digest": confirmation_digest,
        "run_id": run_id,
        "confirmed_at": f"{confirmed_at:.9f}",
        "event_sequence": sequence,
        "anchored_event_id": anchored_event_id,
    }
    current_hash = hashlib.sha256(
        _canonical_json({"label": "user-confirmation-chain-v2", "payload": chain_material}).encode("utf-8"),
    ).hexdigest()
    canonical_payload = {
        "event_type": "USER_CONFIRMATION",
        "run_id": run_id,
        "session_id": session_id,
        "user_id": user_id,
        "tool_name": tool_name,
        "status": "pending",
        "decision": "",
        "event_sequence": sequence,
        "anchored_event_id": anchored_event_id,
        "prior_hash": prior_hash,
        "payload_hash": confirmation_digest,
    }
    canonical_payload_digest = hashlib.sha256(_canonical_json(canonical_payload).encode("utf-8")).hexdigest()
    anchor = {
        "run_id": run_id,
        "event_type": "USER_CONFIRMATION",
        "sequence": sequence,
        "anchored_event_id": anchored_event_id,
        "prior_hash": prior_hash,
        "current_hash": current_hash,
        "payload_hash": confirmation_digest,
        "canonical_payload": canonical_payload,
        "canonical_payload_digest": canonical_payload_digest,
        "chain_material": chain_material,
    }
    anchor["anchor_material_digest"] = hashlib.sha256(
        _canonical_json(
            {
                "label": "gap-anchor-material-v1",
                "payload": {
                    "event_type": anchor["event_type"],
                    "run_id": anchor["run_id"],
                    "sequence": anchor["sequence"],
                    "anchored_event_id": anchor["anchored_event_id"],
                    "prior_hash": anchor["prior_hash"],
                    "payload_hash": anchor["payload_hash"],
                    "canonical_payload_digest": anchor["canonical_payload_digest"],
                },
            },
        ).encode("utf-8"),
    ).hexdigest()
    return anchor


def test_recovery_handshake_and_lockdown_timeline(tmp_path) -> None:
    """Control point: post a handshake then a lockdown uplink into deploy/api.

    Observation point: the backend must return a deterministic shadow hash and a
    fork-point timeline for the operator web without reading edge-local files.
    """

    store = SecurityCenterStore(tmp_path / "store.json")
    client = TestClient(create_app(store))

    handshake = client.post(
        "/security-center/v1/recovery/handshake",
        json={
            "client_id": "edge-a",
            "trace_id": "trace-001",
            "local_hash": "edge-local-hash",
        },
    )
    assert handshake.status_code == 200
    first_shadow_hash = handshake.json()["shadow_hash"]

    repeat = client.post(
        "/security-center/v1/recovery/handshake",
        json={
            "client_id": "edge-a",
            "trace_id": "trace-001",
            "local_hash": "edge-local-hash",
        },
    )
    assert repeat.status_code == 200
    assert repeat.json()["shadow_hash"] == first_shadow_hash

    lockdown = client.post(
        "/security-center/v1/uplinks/lockdowns",
        json={
            "client_id": "edge-a",
            "trace_id": "trace-002",
            "user_id": "employee-security",
            "tool_name": "payroll_export_tool",
            "current_hash": "tampered-local-hash",
            "prior_hash": first_shadow_hash,
            "fork_point_event_id": "forged-edge-fork-point",
            "edge_timestamp_ns": time.time_ns(),
        },
    )
    assert lockdown.status_code == 200

    timeline = client.get("/security-center/v1/operator/timelines/edge-a")
    assert timeline.status_code == 200
    payload = timeline.json()
    assert payload["fork_point"]["event_id"] == "trace-001"
    assert payload["recovery_required"] is True
    assert payload["gap_status"] == "GAP_VALIDATION_REQUIRED"
    assert payload["recovery_gate_status"] == "OPEN"
    assert len(payload["local_hash_curve"]) == 2
    assert len(payload["cloud_shadow_curve"]) == 2
    assert payload["cloud_shadow_curve"][-1]["hash"] != "tampered-local-hash"


def test_recovery_handshake_keeps_gap_validation_required_without_gap_proof(tmp_path) -> None:
    """Control point: call recovery handshake with a local head equal to the
    current cloud shadow hash after a prior lockdown, but do not provide gap proof.

    Observation point: the backend must not mark the client as recovered; it
    must return recovery_required=true and trust_state=GAP_VALIDATION_REQUIRED.
    """

    store = SecurityCenterStore(tmp_path / "store.json")
    client = TestClient(create_app(store))

    lockdown = client.post(
        "/security-center/v1/uplinks/lockdowns",
        json={
            "client_id": "edge-gap-a",
            "trace_id": "trace-gap-001",
            "user_id": "employee-security",
            "tool_name": "payroll_export_tool",
            "current_hash": "tampered-local-hash",
            "prior_hash": "trusted-prior-hash",
            "current_sequence": 7,
            "prior_sequence": 6,
            "anchored_event_id": "edge-anchor-7",
            "prior_anchored_event_id": "edge-anchor-6",
            "edge_timestamp_ns": time.time_ns(),
        },
    )
    assert lockdown.status_code == 200
    cloud_head = lockdown.json()["shadow_hash"]

    handshake = client.post(
        "/security-center/v1/recovery/handshake",
        json={
            "client_id": "edge-gap-a",
            "trace_id": "trace-gap-002",
            "local_hash": cloud_head,
            "checkpoint_hash": cloud_head,
            "local_sequence": 7,
            "checkpoint_sequence": 7,
            "anchored_event_id": "edge-anchor-7",
            "checkpoint_anchor_id": "edge-anchor-7",
        },
    )
    assert handshake.status_code == 200
    payload = handshake.json()
    assert payload["recovery_required"] is True
    assert payload["trust_state"] == "GAP_VALIDATION_REQUIRED"
    assert payload["gap_status"] == "REQUIRED"
    assert payload["recovery_gate_status"] == "OPEN"


def test_recovery_handshake_requires_continuity_evidence_before_direct_alignment(tmp_path) -> None:
    """Control point: establish one trusted anchor, then claim direct shadow-hash alignment without sequence or anchor continuity evidence.

    Observation point: deploy/api must keep recovery_required=true instead of
    clearing trust solely because local_hash equals the current shadow hash.
    """

    store = SecurityCenterStore(tmp_path / "store.json")
    client = TestClient(create_app(store))

    confirmed_at = time.time()
    session_id = "edge-direct-alignment-gap"

    anchor = _build_confirmation_anchor(
        run_id="trace-direct-001",
        session_id=session_id,
        user_id="employee-security",
        tool_name="payroll_export_tool",
        prior_hash=derive_shadow_hash(session_id, "bootstrap"),
        sequence=1,
        anchored_event_id="edge-anchor-1",
        confirmed_at=confirmed_at,
    )

    uplink = client.post(
        "/security-center/v1/uplinks/trusted-anchors",
        json={
            "client_id": session_id,
            "trace_id": "trace-direct-001",
            "run_id": "trace-direct-001",
            "session_id": session_id,
            "event_type": "USER_CONFIRMATION",
            "anchor": anchor,
        },
    )
    assert uplink.status_code == 200
    shadow_hash = uplink.json()["shadow_hash"]

    handshake = client.post(
        "/security-center/v1/recovery/handshake",
        json={
            "client_id": session_id,
            "trace_id": "trace-direct-002",
            "local_hash": shadow_hash,
            "checkpoint_hash": shadow_hash,
        },
    )
    assert handshake.status_code == 200
    payload = handshake.json()
    assert payload["recovery_required"] is True
    assert payload["trust_state"] == "GAP_VALIDATION_REQUIRED"
    assert payload["gap_status"] == "REQUIRED"
    assert payload["divergence_reason"] == "continuity_evidence_missing"


def test_recovery_handshake_rejects_forged_gap_proof_even_when_chain_is_self_consistent(tmp_path) -> None:
    """Control point: submit a gap proof whose sequence and prior/current hash chain are self-consistent.

    Observation point: deploy/api must independently recompute the anchor evidence,
    keep trust_state=GAP_VALIDATION_REQUIRED, and explain that the proof is still untrusted.
    """

    store = SecurityCenterStore(tmp_path / "store.json")
    client = TestClient(create_app(store))

    lockdown = client.post(
        "/security-center/v1/uplinks/lockdowns",
        json={
            "client_id": "edge-gap-forged",
            "trace_id": "trace-gap-forged-001",
            "user_id": "employee-security",
            "tool_name": "payroll_export_tool",
            "current_hash": "tampered-local-hash",
            "prior_hash": "trusted-prior-hash",
            "current_sequence": 7,
            "prior_sequence": 6,
            "anchored_event_id": "edge-anchor-7",
            "prior_anchored_event_id": "edge-anchor-6",
            "edge_timestamp_ns": time.time_ns(),
        },
    )
    assert lockdown.status_code == 200
    cloud_head = lockdown.json()["shadow_hash"]

    timeline = client.get("/security-center/v1/operator/timelines/edge-gap-forged")
    assert timeline.status_code == 200
    trusted_anchor_hash = timeline.json()["last_trusted_anchor_hash"]
    trusted_sequence = timeline.json()["last_trusted_sequence"]
    trusted_anchor_event_id = timeline.json()["last_trusted_anchor_event_id"]

    forged_anchor = {
        "run_id": "trace-gap-forged-002",
        "event_type": "USER_CONFIRMATION",
        "sequence": 7,
        "anchored_event_id": "edge-anchor-7",
        "prior_hash": trusted_anchor_hash,
        "current_hash": cloud_head,
        "payload_hash": "forged-confirmation-digest",
        "canonical_payload": {
            "event_type": "USER_CONFIRMATION",
            "run_id": "trace-gap-forged-002",
            "session_id": "edge-gap-forged",
            "user_id": "employee-security",
            "tool_name": "payroll_export_tool",
            "status": "pending",
            "decision": "",
            "event_sequence": 7,
            "anchored_event_id": "edge-anchor-7",
            "prior_hash": trusted_anchor_hash,
            "payload_hash": "forged-confirmation-digest",
        },
        "canonical_payload_digest": hashlib.sha256(
            _canonical_json(
                {
                    "event_type": "USER_CONFIRMATION",
                    "run_id": "trace-gap-forged-002",
                    "session_id": "edge-gap-forged",
                    "user_id": "employee-security",
                    "tool_name": "payroll_export_tool",
                    "status": "pending",
                    "decision": "",
                    "event_sequence": 7,
                    "anchored_event_id": "edge-anchor-7",
                    "prior_hash": trusted_anchor_hash,
                    "payload_hash": "forged-confirmation-digest",
                },
            ).encode("utf-8"),
        ).hexdigest(),
        "chain_material": {
            "prior_hash": trusted_anchor_hash,
            "confirmation_digest": "forged-confirmation-digest",
            "run_id": "trace-gap-forged-002",
            "confirmed_at": "1700000000.000000000",
            "event_sequence": 7,
            "anchored_event_id": "edge-anchor-7",
        },
    }
    forged_anchor["anchor_material_digest"] = hashlib.sha256(
        _canonical_json(
            {
                "label": "gap-anchor-material-v1",
                "payload": {
                    "event_type": forged_anchor["event_type"],
                    "run_id": forged_anchor["run_id"],
                    "sequence": forged_anchor["sequence"],
                    "anchored_event_id": forged_anchor["anchored_event_id"],
                    "prior_hash": forged_anchor["prior_hash"],
                    "payload_hash": forged_anchor["payload_hash"],
                    "canonical_payload_digest": forged_anchor["canonical_payload_digest"],
                },
            },
        ).encode("utf-8"),
    ).hexdigest()

    handshake = client.post(
        "/security-center/v1/recovery/handshake",
        json={
            "client_id": "edge-gap-forged",
            "trace_id": "trace-gap-forged-003",
            "local_hash": cloud_head,
            "checkpoint_hash": cloud_head,
            "local_sequence": 7,
            "checkpoint_sequence": 7,
            "anchored_event_id": "edge-anchor-7",
            "checkpoint_anchor_id": "edge-anchor-7",
            "gap_proof": {
                "base_anchor_hash": trusted_anchor_hash,
                "base_sequence": trusted_sequence,
                "base_anchor_event_id": trusted_anchor_event_id,
                "head_hash": cloud_head,
                "head_sequence": 7,
                "head_anchor_event_id": "edge-anchor-7",
                "anchors": [forged_anchor],
            },
        },
    )
    assert handshake.status_code == 200
    payload = handshake.json()
    assert payload["trust_state"] == "GAP_VALIDATION_REQUIRED"
    assert payload["recovery_required"] is True
    assert payload["divergence_reason"] == "current_hash_not_recomputable"
    assert payload["gap_status"] == "REQUIRED"


def test_trusted_anchor_uplink_advances_cloud_anchor_and_exposes_provenance(tmp_path) -> None:
    """Control point: post a normal USER_CONFIRMATION trusted-anchor uplink.

    Observation point: the cloud must advance the trusted anchor from the real
    anchor evidence and expose which event advanced it in timeline/overview.
    """

    store = SecurityCenterStore(tmp_path / "store.json")
    client = TestClient(create_app(store))

    bootstrap = client.post(
        "/security-center/v1/recovery/handshake",
        json={
            "client_id": "edge-anchor-a",
            "trace_id": "trace-anchor-bootstrap",
            "local_hash": "",
            "checkpoint_hash": "",
        },
    )
    assert bootstrap.status_code == 422

    bootstrap_hash = hashlib.sha256(
        _canonical_json(
            {
                "client_id": "edge-anchor-a",
                "parts": ["bootstrap"],
                "protocol": "security-center-v1",
            },
        ).encode("utf-8"),
    ).hexdigest()
    anchor = _build_confirmation_anchor(
        run_id="trace-anchor-001",
        session_id="edge-anchor-a",
        user_id="employee-security",
        tool_name="payroll_export_tool",
        prior_hash=bootstrap_hash,
        sequence=1,
        anchored_event_id="anchor-00000001",
        confirmed_at=1700000000.0,
    )

    uplink = client.post(
        "/security-center/v1/uplinks/trusted-anchors",
        json={
            "client_id": "edge-anchor-a",
            "trace_id": "trace-anchor-001",
            "session_id": "edge-anchor-a",
            "event_type": "USER_CONFIRMATION",
            "anchor": anchor,
        },
    )
    assert uplink.status_code == 200
    assert uplink.json()["ack_status"] == "received"

    timeline = client.get("/security-center/v1/operator/timelines/edge-anchor-a")
    assert timeline.status_code == 200
    timeline_payload = timeline.json()
    assert timeline_payload["trust_state"] == "ALIGNED"
    assert timeline_payload["last_trusted_anchor_event_id"] == "anchor-00000001"
    assert timeline_payload["last_trusted_anchor_source"] == "trusted_anchor_uplink"
    assert timeline_payload["last_trusted_anchor_trace_id"] == "trace-anchor-001"
    assert timeline_payload["last_trusted_anchor_event_type"] == "USER_CONFIRMATION"

    overview = client.get("/security-center/v1/operator/overview")
    assert overview.status_code == 200
    client_state = overview.json()["clients"][0]
    assert client_state["last_trusted_anchor_source"] == "trusted_anchor_uplink"
    assert client_state["last_trusted_anchor_event_type"] == "USER_CONFIRMATION"


def test_rejection_uplink_exposes_voucher_and_overview(tmp_path) -> None:
    """Control point: post a Security_Rejection_Nonce uplink to deploy/api.

    Observation point: the backend must persist the rejected event, expose a
    voucher lookup surface, and include the alert in operator overview.
    """

    store = SecurityCenterStore(tmp_path / "store.json")
    client = TestClient(create_app(store))

    response = client.post(
        "/security-center/v1/uplinks/rejections",
        json={
            "client_id": "edge-b",
            "trace_id": "trace-003",
            "user_id": "employee-red-team",
            "tool_name": "payroll_export_tool",
            "security_rejection_nonce": "nonce-1234567890abcdef",
            "current_hash": "trace-hash",
            "edge_timestamp_ns": time.time_ns(),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    voucher = client.get(payload["voucher_url"])
    assert voucher.status_code == 200
    assert voucher.json()["voucher"] == "Voucher:nonce-1234567890abcdef"

    overview = client.get("/security-center/v1/operator/overview")
    assert overview.status_code == 200
    assert overview.json()["rejection_count"] == 1


def test_uplinks_require_edge_timestamp_ns(tmp_path) -> None:
    """Control point: post rejection and lockdown uplinks without edge timestamps.

    Observation point: deploy/api must reject both requests instead of fabricating
    server-side timing for anti-cheat latency calculations.
    """

    store = SecurityCenterStore(tmp_path / "store.json")
    client = TestClient(create_app(store))

    rejection = client.post(
        "/security-center/v1/uplinks/rejections",
        json={
            "client_id": "edge-c",
            "trace_id": "trace-004",
            "user_id": "employee-red-team",
            "tool_name": "payroll_export_tool",
            "security_rejection_nonce": "nonce-abcdef1234567890",
            "current_hash": "trace-hash",
        },
    )
    assert rejection.status_code == 422

    lockdown = client.post(
        "/security-center/v1/uplinks/lockdowns",
        json={
            "client_id": "edge-c",
            "trace_id": "trace-005",
            "user_id": "employee-security",
            "tool_name": "payroll_export_tool",
            "current_hash": "tampered-local-hash",
            "prior_hash": "shadow-prior-hash",
        },
    )
    assert lockdown.status_code == 422
