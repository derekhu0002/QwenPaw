from __future__ import annotations

import time

from fastapi.testclient import TestClient

from deploy.api.app import create_app
from deploy.api.store import SecurityCenterStore


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
    assert len(payload["local_hash_curve"]) == 2
    assert len(payload["cloud_shadow_curve"]) == 2
    assert payload["cloud_shadow_curve"][-1]["hash"] != "tampered-local-hash"


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
