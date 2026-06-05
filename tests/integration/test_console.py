# -*- coding: utf-8 -*-
"""Integration tests for console routes (no LLM / no external API keys)."""
from __future__ import annotations

import io
import uuid

import httpx
import pytest

_CONSOLE_HTTP_TIMEOUT = 30.0


def _submit_high_risk_console_prompt(
    app_server,
    *,
    user_id: str,
    session_id: str,
    prompt: str,
) -> httpx.Response:
    payload = {
        "channel": "console",
        "user_id": user_id,
        "session_id": session_id,
        "input": [
            {
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    }
                ]
            }
        ],
    }
    return app_server.api_request(
        "POST",
        "/api/console/chat",
        json=payload,
        headers={"accept": "text/event-stream"},
        timeout=httpx.Timeout(_CONSOLE_HTTP_TIMEOUT, read=_CONSOLE_HTTP_TIMEOUT),
    )


@pytest.mark.integration
@pytest.mark.p0
def test_agent_scoped_console_chat_stop_no_running_task(app_server) -> None:
    """Test purpose:
    - Verify scoped console chat/stop returns a stable JSON contract when no
      stream is attached for the given chat id (no model call).

    Test flow:
    1. Create a dedicated test agent.
    2. POST /console/chat/stop with a random UUID chat_id.
    3. Assert 200 and ``stopped`` is a boolean (typically False).
    4. Delete test agent.

    API endpoints:
    - POST /api/agents
    - POST /api/agents/{agentId}/console/chat/stop
    - DELETE /api/agents/{agentId}
    """
    agent_id = "integ_console_stop_01"
    fake_chat_id = str(uuid.uuid4())

    create_agent = app_server.api_request(
        "POST",
        "/api/agents",
        json={"id": agent_id, "name": "Console stop agent", "description": ""},
    )
    assert create_agent.status_code == 201, app_server.logs_tail()

    try:
        stop_url = (
            f"{app_server.base_url}/api/agents/{agent_id}/console/chat/stop"
            f"?chat_id={fake_chat_id}"
        )
        resp = app_server.client.post(stop_url, timeout=_CONSOLE_HTTP_TIMEOUT)
        print(
            (
                f"[integration]"
                f"[{'PASS' if resp.status_code == 200 else 'FAIL'}] "
                f"POST /api/agents/{agent_id}/console/chat/stop | "
                f"params=chat_id={fake_chat_id} | request=- | "
                f"status={resp.status_code} | response={resp.text[:500]}"
            ),
            flush=True,
        )
        assert resp.status_code == 200, app_server.logs_tail()
        body = resp.json()
        assert isinstance(body.get("stopped"), bool)
    finally:
        app_server.api_request("DELETE", f"/api/agents/{agent_id}")


@pytest.mark.integration
@pytest.mark.p0
def test_agent_scoped_console_upload_small_file(app_server) -> None:
    """Test purpose:
    - Verify scoped console upload accepts a small file and returns metadata
      without calling external services.

    Test flow:
    1. Create a dedicated test agent.
    2. POST multipart upload to scoped console upload with tiny text content.
    3. Assert JSON includes file_name and expected byte size.
    4. Delete test agent.

    API endpoints:
    - POST /api/agents
    - POST /api/agents/{agentId}/console/upload
    - DELETE /api/agents/{agentId}
    """
    agent_id = "integ_console_upload_01"
    payload = b"integration-console-upload\n"

    create_agent = app_server.api_request(
        "POST",
        "/api/agents",
        json={
            "id": agent_id,
            "name": "Console upload agent",
            "description": "",
        },
    )
    assert create_agent.status_code == 201, app_server.logs_tail()

    try:
        upload_url = (
            f"{app_server.base_url}/api/agents/{agent_id}/console/upload"
        )
        files = {
            "file": ("integ-upload.txt", io.BytesIO(payload), "text/plain"),
        }
        resp = app_server.client.post(
            upload_url,
            files=files,
            timeout=_CONSOLE_HTTP_TIMEOUT,
        )
        print(
            (
                f"[integration]"
                f"[{'PASS' if resp.status_code == 200 else 'FAIL'}] "
                f"POST /api/agents/{agent_id}/console/upload | "
                f"params=- | request=(multipart file) | "
                f"status={resp.status_code} | response={resp.text[:800]}"
            ),
            flush=True,
        )
        assert resp.status_code == 200, app_server.logs_tail()
        body = resp.json()
        assert body.get("file_name") == "integ-upload.txt"
        assert body.get("size") == len(payload)
        assert "url" in body
    finally:
        app_server.api_request("DELETE", f"/api/agents/{agent_id}")


@pytest.mark.integration
@pytest.mark.p0
def test_console_chat_returns_423_when_resumed_sensitive_action_hits_untrusted_runtime(app_server) -> None:
    """Control point: create one high-risk console flow, delete the active
    checkpoint, then submit a resumed sensitive action through /api/console/chat.

    Observation point: the business boundary must reject with 423 and surface
    explicit UNTRUSTED recovery state instead of relying on frontend-only hints.
    """

    session_id = "integ-console-untrusted-runtime-session"
    user_id = "employee_security_auditor"
    baseline_prompt = (
        "As authenticated employee employee_security_auditor, ask "
        "security_audit_agent to use plugin security_center_backend_api and "
        "high-risk tool payroll_export_tool. Confirmation phrase: Approve audit "
        "integrity baseline capture."
    )
    baseline_resp = _submit_high_risk_console_prompt(
        app_server,
        user_id=user_id,
        session_id=session_id,
        prompt=baseline_prompt,
    )
    assert baseline_resp.status_code == 200, app_server.logs_tail()

    checkpoint_path = app_server.working_dir / "audit_chain_checkpoint.json"
    assert checkpoint_path.exists(), app_server.logs_tail()
    checkpoint_path.unlink()

    resumed_resp = _submit_high_risk_console_prompt(
        app_server,
        user_id=user_id,
        session_id=session_id,
        prompt="Resume payroll close reconciliation with high-risk tool payroll_export_tool after reconnect.",
    )
    assert resumed_resp.status_code == 423, app_server.logs_tail()
    assert "UNTRUSTED" in resumed_resp.text, app_server.logs_tail()
