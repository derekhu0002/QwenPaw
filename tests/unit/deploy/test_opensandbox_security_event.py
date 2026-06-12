from __future__ import annotations

from fastapi.testclient import TestClient

from deploy.api.app import create_app
from deploy.api.store import SecurityCenterStore


def test_accepts_opensandbox_debug_audit_event(tmp_path) -> None:
    """Normal OpenSandbox executions are retained as DEBUG audit history."""
    client = TestClient(
        create_app(SecurityCenterStore(tmp_path / "opensandbox-store.json")),
    )
    event = {
        "sourceSystem": "opensandbox",
        "eventId": "opensandbox-debug-001",
        "eventTypeId": "opensandbox",
        "schemaVersion": "1.0",
        "severity": "DEBUG",
        "summary": "OpenSandbox MCP command_run succeeded",
        "occurredAt": "2026-06-12T08:00:00Z",
        "payload": {
            "toolName": "command_run",
            "operationClass": "EXECUTION",
            "outcome": "SUCCEEDED",
            "agentId": "agent-test",
            "sandboxId": "sandbox-1",
            "durationMs": 17,
            "requestDigest": "a" * 64,
            "argumentSummary": {"command": {"preview": "true"}},
        },
    }

    response = client.post("/security-center/v1/events", json=event)
    assert response.status_code == 200
    assert response.json()["success"] is True

    listing = client.get(
        "/security-center/v1/operator/events",
        params={
            "sourceSystem": "opensandbox",
            "eventTypeId": "opensandbox",
            "severity": "DEBUG",
        },
    )
    assert listing.status_code == 200
    assert listing.json()["events"] == [
        {
            "sourceSystem": "opensandbox",
            "eventId": "opensandbox-debug-001",
            "eventTypeId": "opensandbox",
            "eventTypeDisplayName": "OpenSandbox",
            "schemaVersion": "1.0",
            "severity": "DEBUG",
            "summary": "OpenSandbox MCP command_run succeeded",
            "occurredAt": "2026-06-12T08:00:00Z",
            "receivedAt": response.json()["receivedAt"],
            "toolName": "command_run",
            "outcome": "SUCCEEDED",
            "agentId": "agent-test",
            "sandboxId": "sandbox-1",
        },
    ]
