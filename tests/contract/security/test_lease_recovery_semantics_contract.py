# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest

from qwenpaw.security.audit_foundation import _build_gap_proof as build_runtime_gap_proof
from tests.integration.conftest import (  # noqa: F401
    AppServer,
    _find_free_port,
    _tee_stream,
    _wait_for_http_ready,
    _wait_for_log_marker,
    app_server,
)

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


def _poll_recovered_timeline(app_server, *, client_id: str) -> dict[str, object] | None:
    deadline = time.time() + 15.0
    last_timeline: dict[str, object] | None = None
    while time.time() < deadline:
        timeline = _read_security_center_timeline(app_server, client_id=client_id)
        if isinstance(timeline, dict):
            last_timeline = timeline
            if (
                str(timeline.get("trust_state") or "") in {TRUST_STATE_ALIGNED, "TRUSTED"}
                and str(timeline.get("gap_status") or "") in {GAP_STATUS_CLEAR, "VALIDATED"}
                and timeline.get("recovery_gate_status") == RECOVERY_GATE_CLOSED
                and timeline.get("recovery_required") is False
                and int(timeline.get("lease_expires_at") or 0) > time.time_ns()
            ):
                return timeline
        time.sleep(0.25)
    return last_timeline


@pytest.fixture
def live_reconnect_server(tmp_path: Path) -> AppServer:
    repo_root = Path(__file__).resolve().parents[3]
    src_root = repo_root / "src"
    host = "127.0.0.1"
    port = _find_free_port(host)

    working_dir = tmp_path / "working"
    secret_dir = tmp_path / "working.secret"
    backups_dir = tmp_path / "working.backups"
    security_center_data_dir = tmp_path / "security-center-data"
    for directory in (working_dir, secret_dir, backups_dir, security_center_data_dir):
        directory.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["QWENPAW_WORKING_DIR"] = str(working_dir)
    env["QWENPAW_SECRET_DIR"] = str(secret_dir)
    env["QWENPAW_BACKUP_DIR"] = str(backups_dir)
    env["QWENPAW_AUTH_ENABLED"] = "false"
    env["NO_PROXY"] = "*"
    env["PYTHONUNBUFFERED"] = "1"
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = (
        str(src_root)
        if not existing_pythonpath
        else os.pathsep.join((str(src_root), existing_pythonpath))
    )
    env["PYTHONIOENCODING"] = "utf-8"

    security_center_api_port = _find_free_port(host)
    security_center_web_port = _find_free_port(host)
    security_center_api_url = f"http://{host}:{security_center_api_port}"
    security_center_web_url = f"http://{host}:{security_center_web_port}"
    env["QWENPAW_SECURITY_CENTER_API_URL"] = security_center_api_url
    env["QWENPAW_SECURITY_CENTER_WEB_URL"] = security_center_web_url

    security_center_env = env.copy()
    security_center_env["SECURITY_CENTER_API_HOST"] = host
    security_center_env["SECURITY_CENTER_API_PORT"] = str(security_center_api_port)
    security_center_env["QWENPAW_SECURITY_CENTER_DATA_DIR"] = str(security_center_data_dir)

    security_center_web_env = env.copy()
    security_center_web_env["SECURITY_CENTER_WEB_HOST"] = host
    security_center_web_env["SECURITY_CENTER_WEB_PORT"] = str(security_center_web_port)
    security_center_web_env["SECURITY_CENTER_API_BASE"] = security_center_api_url

    logs: list[str] = []
    security_center_api_logs: list[str] = []
    security_center_web_logs: list[str] = []
    client = httpx.Client(timeout=30.0, trust_env=False)

    security_center_api_process = subprocess.Popen(
        [sys.executable, "-m", "deploy.api.app"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
        env=security_center_env,
        cwd=repo_root,
    )
    security_center_web_process = subprocess.Popen(
        [sys.executable, "-m", "deploy.web.server"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
        env=security_center_web_env,
        cwd=repo_root,
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "qwenpaw",
            "app",
            "--host",
            host,
            "--port",
            str(port),
            "--log-level",
            "info",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=repo_root,
    )

    assert security_center_api_process.stdout is not None
    assert security_center_web_process.stdout is not None
    assert process.stdout is not None

    security_center_api_log_thread = threading.Thread(
        target=_tee_stream,
        args=(security_center_api_process.stdout, security_center_api_logs),
        daemon=True,
    )
    security_center_api_log_thread.start()

    security_center_web_log_thread = threading.Thread(
        target=_tee_stream,
        args=(security_center_web_process.stdout, security_center_web_logs),
        daemon=True,
    )
    security_center_web_log_thread.start()

    log_thread = threading.Thread(
        target=_tee_stream,
        args=(process.stdout, logs),
        daemon=True,
    )
    log_thread.start()

    startup_error = _wait_for_http_ready(
        client,
        url=f"{security_center_api_url}/security-center/v1/health",
        ready_statuses={200},
        timeout_seconds=15.0,
        process=security_center_api_process,
        logs=security_center_api_logs,
        service_name="Security Center API",
    )
    if startup_error is None:
        startup_error = _wait_for_http_ready(
            client,
            url=f"{security_center_web_url}/",
            ready_statuses={200},
            timeout_seconds=15.0,
            process=security_center_web_process,
            logs=security_center_web_logs,
            service_name="Security Center web",
        )

    if startup_error is None:
        start_at = time.time()
        last_error: str | None = None
        while time.time() - start_at < 60.0:
            if process.poll() is not None:
                startup_error = (
                    "qwenpaw app exited during startup.\n"
                    f"exit_code={process.returncode}\n"
                    f"logs:\n{''.join(logs)[-4000:]}"
                )
                break
            try:
                response = client.get(f"http://{host}:{port}/api/version")
                if response.status_code == 200:
                    startup_error = _wait_for_log_marker(
                        marker="Background startup completed",
                        timeout_seconds=20.0,
                        process=process,
                        logs=logs,
                        service_name="qwenpaw app",
                    )
                    break
                last_error = f"unexpected status {response.status_code}"
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_error = str(exc)
            time.sleep(0.5)
        else:
            startup_error = (
                "qwenpaw app did not become ready in time.\n"
                f"last_error={last_error}\n"
                f"logs:\n{''.join(logs)[-4000:]}"
            )

    server = AppServer(
        host=host,
        port=port,
        process=process,
        client=client,
        logs=logs,
        log_thread=log_thread,
        working_dir=working_dir,
        security_center_data_dir=security_center_data_dir,
        startup_error=startup_error,
        security_center_api_url=security_center_api_url,
        security_center_web_url=security_center_web_url,
        security_center_api_process=security_center_api_process,
        security_center_web_process=security_center_web_process,
        security_center_api_logs=security_center_api_logs,
        security_center_web_logs=security_center_web_logs,
        security_center_api_log_thread=security_center_api_log_thread,
        security_center_web_log_thread=security_center_web_log_thread,
    )

    try:
        yield server
    finally:
        client.close()
        if process.poll() is None:
            try:
                if sys.platform == "win32":
                    process.terminate()
                else:
                    process.send_signal(signal.SIGINT)
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        log_thread.join(timeout=2)
        for extra_process in (security_center_web_process, security_center_api_process):
            if extra_process.poll() is None:
                extra_process.terminate()
                try:
                    extra_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    extra_process.kill()
                    extra_process.wait(timeout=5)
        security_center_api_log_thread.join(timeout=2)
        security_center_web_log_thread.join(timeout=2)


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


@pytest.mark.contract
@pytest.mark.p0
def test_security_center_live_reconnect_gap_proof_restores_access(
    live_reconnect_server: AppServer,
) -> None:
    """Control point: start Security Center API/Web and one real QwenPaw
    runtime from a reset state, establish a trusted anchor, let the same
    canonical client downgrade to UNTRUSTED after TTL expiry, then restart the
    same runtime and attempt restored model access without manually posting a
    proof to deploy/api.

    Observation point: the real runtime re-online path must automatically use
    the locally constructible full missing-gap proof, close the recovery gate,
    refresh canonical lease timing, and stop returning 423 recovery-gated
    blocking once Security Center projects recovery_required=false.
    """

    if live_reconnect_server.startup_error is not None:
        raise AssertionError(live_reconnect_server.startup_error)

    recovery_session_id = "security-center-live-reconnect-recovery-contract"
    operator_user_id = "security_contract_operator"
    trusted_anchor_prompt = (
        "Warm the runtime for lease heartbeat monitoring before the "
        "Security Center lease window expires."
    )
    restored_access_prompt = (
        "Resume normal model access for the previously trusted device "
        "after the lease window elapsed, with missing-gap verification "
        "evidence completed."
    )

    # // GIVEN
    projected_overview, projected_client = _poll_projected_lease_client(live_reconnect_server)
    canonical_client_id = str(projected_client.get("canonical_client_id") or "").strip()
    assert canonical_client_id, (
        "Live_Reconnect_Setup_Gap: the reset-state runtime must first project a "
        "canonical lease-bearing client before offline downgrade and reconnect recovery can be observed; "
        f"observed overview={projected_overview!r}."
    )
    trusted_anchor_status = _submit_console_prompt(
        live_reconnect_server,
        user_id=operator_user_id,
        session_id=recovery_session_id,
        prompt=trusted_anchor_prompt,
    )
    assert trusted_anchor_status == 200, (
        "Live_Reconnect_Setup_Gap: the test must establish session-scoped local "
        "trace evidence before isolating runtime reconnect recovery."
    )
    if live_reconnect_server.process.poll() is None:
        live_reconnect_server.process.terminate()
        live_reconnect_server.process.wait(timeout=15)
    expired_timeline = _poll_ttl_expired_timeline(
        live_reconnect_server,
        client_id=canonical_client_id,
    )

    restarted_runtime_logs: list[str] = []
    repo_root = Path(__file__).resolve().parents[3]
    restarted_runtime_env = os.environ.copy()
    restarted_runtime_env["QWENPAW_WORKING_DIR"] = str(live_reconnect_server.working_dir)
    restarted_runtime_env["QWENPAW_SECRET_DIR"] = str(live_reconnect_server.working_dir.parent / "working.secret")
    restarted_runtime_env["QWENPAW_BACKUP_DIR"] = str(live_reconnect_server.working_dir.parent / "working.backups")
    restarted_runtime_env["QWENPAW_AUTH_ENABLED"] = "false"
    restarted_runtime_env["NO_PROXY"] = "*"
    restarted_runtime_env["PYTHONUNBUFFERED"] = "1"
    existing_pythonpath = restarted_runtime_env.get("PYTHONPATH", "").strip()
    restarted_runtime_env["PYTHONPATH"] = (
        str(repo_root / "src")
        if not existing_pythonpath
        else os.pathsep.join((str(repo_root / "src"), existing_pythonpath))
    )
    restarted_runtime_env["PYTHONIOENCODING"] = "utf-8"
    assert live_reconnect_server.security_center_api_url is not None
    assert live_reconnect_server.security_center_web_url is not None
    restarted_runtime_env["QWENPAW_SECURITY_CENTER_API_URL"] = live_reconnect_server.security_center_api_url
    restarted_runtime_env["QWENPAW_SECURITY_CENTER_WEB_URL"] = live_reconnect_server.security_center_web_url

    restarted_runtime_process: subprocess.Popen[str] | None = None
    restarted_runtime_log_thread: threading.Thread | None = None
    try:
        # // WHEN
        restarted_runtime_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "qwenpaw",
                "app",
                "--host",
                live_reconnect_server.host,
                "--port",
                str(live_reconnect_server.port),
                "--log-level",
                "info",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
            env=restarted_runtime_env,
            cwd=repo_root,
        )
        assert restarted_runtime_process.stdout is not None
        restarted_runtime_log_thread = threading.Thread(
            target=_tee_stream,
            args=(restarted_runtime_process.stdout, restarted_runtime_logs),
            daemon=True,
        )
        restarted_runtime_log_thread.start()

        restart_ready_error = _wait_for_http_ready(
            live_reconnect_server.client,
            url=f"{live_reconnect_server.base_url}/api/version",
            ready_statuses={200},
            timeout_seconds=30.0,
            process=restarted_runtime_process,
            logs=restarted_runtime_logs,
            service_name="qwenpaw app",
        )
        assert restart_ready_error is None, restart_ready_error

        restored_access_status = _submit_console_prompt(
            live_reconnect_server,
            user_id=operator_user_id,
            session_id=recovery_session_id,
            prompt=restored_access_prompt,
        )
        local_gap_proof = build_runtime_gap_proof(
            base_dir=live_reconnect_server.working_dir,
            session_id=recovery_session_id,
        )
        recovered_timeline = _poll_recovered_timeline(
            live_reconnect_server,
            client_id=canonical_client_id,
        )
        recovered_overview = _read_security_center_overview(live_reconnect_server)
        recovered_store = _read_security_center_store_snapshot(live_reconnect_server)
        recovered_clients = recovered_store.get("clients") if isinstance(recovered_store, dict) else {}
        recovered_client = recovered_clients.get(canonical_client_id, {}) if isinstance(recovered_clients, dict) else {}

        # // THEN
        assert isinstance(expired_timeline, dict), (
            "Live_Reconnect_Setup_Gap: Security Center must first expose the "
            "canonical runtime as lease_ttl_expired before reconnect recovery can be judged."
        )
        assert expired_timeline.get("trust_state") == TRUST_STATE_UNTRUSTED, (
            "Live_Reconnect_Setup_Gap: the same canonical client must degrade to "
            f"UNTRUSTED before reconnect recovery is observed. Timeline={expired_timeline!r}."
        )
        assert expired_timeline.get("divergence_reason") == "lease_ttl_expired", (
            "Live_Reconnect_Setup_Gap: reconnect recovery must begin from a true "
            f"lease-expired client, not from a different divergence category. Timeline={expired_timeline!r}."
        )
        assert local_gap_proof.get("anchors"), (
            "Live_Reconnect_Recovery_Gap: the restarted runtime still failed to "
            "produce a locally constructible full missing-gap proof for the same session, "
            "so the guard cannot yet distinguish missing evidence from missing automation."
        )
        assert restored_access_status == 200, (
            "Live_Reconnect_Recovery_Gap: after the same runtime comes back online, "
            "the edge-side restored access path must stop returning 423 once locally "
            "recoverable gap evidence exists."
        )
        assert isinstance(recovered_timeline, dict), (
            "Live_Reconnect_Recovery_Gap: Security Center must expose a recovered "
            "timeline for the same canonical client after runtime restart."
        )
        assert str(recovered_timeline.get("trust_state") or "") in {TRUST_STATE_ALIGNED, "TRUSTED"}, (
            "Live_Reconnect_Recovery_Gap: the same canonical client must return to "
            f"ALIGNED or TRUSTED after automatic reconnect recovery. Timeline={recovered_timeline!r}."
        )
        assert str(recovered_timeline.get("gap_status") or "") in {GAP_STATUS_CLEAR, "VALIDATED"}, (
            "Live_Reconnect_Recovery_Gap: the reconnect recovery path must close or "
            f"validate the missing gap before restored access succeeds. Timeline={recovered_timeline!r}."
        )
        assert recovered_timeline.get("recovery_gate_status") == RECOVERY_GATE_CLOSED, (
            "Live_Reconnect_Recovery_Gap: the real reconnect path must close the "
            f"recovery gate before restored access succeeds. Timeline={recovered_timeline!r}."
        )
        assert recovered_timeline.get("recovery_required") is False, (
            "Live_Reconnect_Recovery_Gap: the same canonical client must not remain "
            f"recovery_required after runtime restart and automatic proof submission. Timeline={recovered_timeline!r}."
        )
        assert int(recovered_timeline.get("lease_expires_at") or 0) > time.time_ns(), (
            "Live_Reconnect_Recovery_Gap: the recovered client must refresh lease "
            f"timing beyond the observation instant, not fall back to stale expiry. Timeline={recovered_timeline!r}."
        )
        assert int(recovered_client.get("lease_expires_at") or 0) > time.time_ns(), (
            "Live_Reconnect_Recovery_Gap: the durable Security Center store must "
            "refresh lease expiry for the same canonical client once reconnect recovery succeeds."
        )
        overview_clients = recovered_overview.get("clients") if isinstance(recovered_overview, dict) else []
        matching_clients = [
            client
            for client in overview_clients
            if isinstance(client, dict)
            and str(client.get("canonical_client_id") or "").strip() == canonical_client_id
        ]
        assert any(
            str(client.get("trust_state") or "") in {TRUST_STATE_ALIGNED, "TRUSTED"}
            and client.get("recovery_gate_status") == RECOVERY_GATE_CLOSED
            and client.get("recovery_required") is False
            for client in matching_clients
        ), (
            "Live_Reconnect_Recovery_Gap: operator overview must show the same "
            "canonical client as recovered after runtime restart, rather than leaving it blocked."
        )
    finally:
        if restarted_runtime_process is not None and restarted_runtime_process.poll() is None:
            restarted_runtime_process.terminate()
            try:
                restarted_runtime_process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                restarted_runtime_process.kill()
                restarted_runtime_process.wait(timeout=5)
        if restarted_runtime_log_thread is not None:
            restarted_runtime_log_thread.join(timeout=2)


@pytest.mark.contract
@pytest.mark.p0
def test_security_center_passive_reconnect_auto_restores_operator_view(
    live_reconnect_server: AppServer,
) -> None:
    """Control point: start Security Center API/Web and one real QwenPaw
    runtime from a reset state, establish a trusted anchor, let the same
    canonical client downgrade to UNTRUSTED after TTL expiry, then restart the
    same runtime and observe Security Center before any restored-access prompt
    is executed.

    Observation point: passive reconnect heartbeat must automatically
    materialize accepted missing-gap evidence, close the recovery gate for the
    same canonical client, refresh lease timing, and return the operator view
    to a normal aligned state without requiring a restored-access prompt.
    """

    if live_reconnect_server.startup_error is not None:
        raise AssertionError(live_reconnect_server.startup_error)

    recovery_session_id = "security-center-passive-reconnect-contract"
    operator_user_id = "security_contract_operator"
    trusted_anchor_prompt = (
        "Warm the runtime for lease heartbeat monitoring before the "
        "Security Center lease window expires."
    )

    projected_overview, projected_client = _poll_projected_lease_client(live_reconnect_server)
    canonical_client_id = str(projected_client.get("canonical_client_id") or "").strip()
    assert canonical_client_id, (
        "Passive_Reconnect_Setup_Gap: the reset-state runtime must first project a "
        "canonical lease-bearing client before offline downgrade and reconnect recovery can be observed; "
        f"observed overview={projected_overview!r}."
    )
    trusted_anchor_status = _submit_console_prompt(
        live_reconnect_server,
        user_id=operator_user_id,
        session_id=recovery_session_id,
        prompt=trusted_anchor_prompt,
    )
    assert trusted_anchor_status == 200, (
        "Passive_Reconnect_Setup_Gap: the test must establish session-scoped local "
        "trace evidence before isolating passive reconnect recovery."
    )
    if live_reconnect_server.process.poll() is None:
        live_reconnect_server.process.terminate()
        live_reconnect_server.process.wait(timeout=15)
    expired_timeline = _poll_ttl_expired_timeline(
        live_reconnect_server,
        client_id=canonical_client_id,
    )

    restarted_runtime_logs: list[str] = []
    repo_root = Path(__file__).resolve().parents[3]
    restarted_runtime_env = os.environ.copy()
    restarted_runtime_env["QWENPAW_WORKING_DIR"] = str(live_reconnect_server.working_dir)
    restarted_runtime_env["QWENPAW_SECRET_DIR"] = str(live_reconnect_server.working_dir.parent / "working.secret")
    restarted_runtime_env["QWENPAW_BACKUP_DIR"] = str(live_reconnect_server.working_dir.parent / "working.backups")
    restarted_runtime_env["QWENPAW_AUTH_ENABLED"] = "false"
    restarted_runtime_env["NO_PROXY"] = "*"
    restarted_runtime_env["PYTHONUNBUFFERED"] = "1"
    existing_pythonpath = restarted_runtime_env.get("PYTHONPATH", "").strip()
    restarted_runtime_env["PYTHONPATH"] = (
        str(repo_root / "src")
        if not existing_pythonpath
        else os.pathsep.join((str(repo_root / "src"), existing_pythonpath))
    )
    restarted_runtime_env["PYTHONIOENCODING"] = "utf-8"
    assert live_reconnect_server.security_center_api_url is not None
    assert live_reconnect_server.security_center_web_url is not None
    restarted_runtime_env["QWENPAW_SECURITY_CENTER_API_URL"] = live_reconnect_server.security_center_api_url
    restarted_runtime_env["QWENPAW_SECURITY_CENTER_WEB_URL"] = live_reconnect_server.security_center_web_url

    restarted_runtime_process: subprocess.Popen[str] | None = None
    restarted_runtime_log_thread: threading.Thread | None = None
    try:
        restarted_runtime_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "qwenpaw",
                "app",
                "--host",
                live_reconnect_server.host,
                "--port",
                str(live_reconnect_server.port),
                "--log-level",
                "info",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
            env=restarted_runtime_env,
            cwd=repo_root,
        )
        assert restarted_runtime_process.stdout is not None
        restarted_runtime_log_thread = threading.Thread(
            target=_tee_stream,
            args=(restarted_runtime_process.stdout, restarted_runtime_logs),
            daemon=True,
        )
        restarted_runtime_log_thread.start()

        restart_ready_error = _wait_for_http_ready(
            live_reconnect_server.client,
            url=f"{live_reconnect_server.base_url}/api/version",
            ready_statuses={200},
            timeout_seconds=30.0,
            process=restarted_runtime_process,
            logs=restarted_runtime_logs,
            service_name="qwenpaw app",
        )
        assert restart_ready_error is None, restart_ready_error

        recovered_timeline = _poll_recovered_timeline(
            live_reconnect_server,
            client_id=canonical_client_id,
        )
        recovered_overview = _read_security_center_overview(live_reconnect_server)
        recovered_store = _read_security_center_store_snapshot(live_reconnect_server)
        recovered_clients = recovered_store.get("clients") if isinstance(recovered_store, dict) else {}
        recovered_client = recovered_clients.get(canonical_client_id, {}) if isinstance(recovered_clients, dict) else {}
        local_gap_proof = build_runtime_gap_proof(
            base_dir=live_reconnect_server.working_dir,
            session_id=recovery_session_id,
        )

        assert isinstance(expired_timeline, dict), (
            "Passive_Reconnect_Setup_Gap: Security Center must first expose the "
            "canonical runtime as lease_ttl_expired before passive reconnect recovery can be judged."
        )
        assert expired_timeline.get("trust_state") == TRUST_STATE_UNTRUSTED, (
            "Passive_Reconnect_Setup_Gap: the same canonical client must degrade to "
            f"UNTRUSTED before passive reconnect recovery is observed. Timeline={expired_timeline!r}."
        )
        assert expired_timeline.get("divergence_reason") == "lease_ttl_expired", (
            "Passive_Reconnect_Setup_Gap: passive reconnect recovery must begin from a true "
            f"lease-expired client, not from a different divergence category. Timeline={expired_timeline!r}."
        )
        assert local_gap_proof.get("anchors"), (
            "Passive_Reconnect_Recovery_Gap: runtime reconnect heartbeat failed to "
            "materialize a locally constructible missing-gap proof before any restored-access prompt ran."
        )
        assert isinstance(recovered_timeline, dict), (
            "Passive_Reconnect_Recovery_Gap: Security Center must expose a recovered "
            "timeline for the same canonical client after runtime restart alone."
        )
        assert str(recovered_timeline.get("trust_state") or "") in {TRUST_STATE_ALIGNED, "TRUSTED"}, (
            "Passive_Reconnect_Recovery_Gap: passive reconnect must return the same "
            f"canonical client to ALIGNED or TRUSTED before any restored-access prompt. Timeline={recovered_timeline!r}."
        )
        assert str(recovered_timeline.get("gap_status") or "") in {GAP_STATUS_CLEAR, "VALIDATED"}, (
            "Passive_Reconnect_Recovery_Gap: passive reconnect must clear or validate "
            f"the missing gap before operator recovery is projected. Timeline={recovered_timeline!r}."
        )
        assert recovered_timeline.get("recovery_gate_status") == RECOVERY_GATE_CLOSED, (
            "Passive_Reconnect_Recovery_Gap: passive reconnect heartbeat must close the "
            f"recovery gate before operator view normalizes. Timeline={recovered_timeline!r}."
        )
        assert recovered_timeline.get("recovery_required") is False, (
            "Passive_Reconnect_Recovery_Gap: the same canonical client must stop being "
            f"recovery_required on reconnect alone. Timeline={recovered_timeline!r}."
        )
        assert int(recovered_timeline.get("lease_expires_at") or 0) > time.time_ns(), (
            "Passive_Reconnect_Recovery_Gap: the recovered client must refresh lease "
            f"timing beyond the observation instant, not fall back to stale expiry. Timeline={recovered_timeline!r}."
        )
        assert int(recovered_client.get("lease_expires_at") or 0) > time.time_ns(), (
            "Passive_Reconnect_Recovery_Gap: the durable Security Center store must "
            "refresh lease expiry for the same canonical client once passive reconnect succeeds."
        )
        overview_clients = recovered_overview.get("clients") if isinstance(recovered_overview, dict) else []
        matching_clients = [
            client
            for client in overview_clients
            if isinstance(client, dict)
            and str(client.get("canonical_client_id") or "").strip() == canonical_client_id
        ]
        assert any(
            str(client.get("trust_state") or "") in {TRUST_STATE_ALIGNED, "TRUSTED"}
            and client.get("recovery_gate_status") == RECOVERY_GATE_CLOSED
            and client.get("recovery_required") is False
            for client in matching_clients
        ), (
            "Passive_Reconnect_Recovery_Gap: operator overview must show the same "
            "canonical client as recovered after reconnect heartbeat alone."
        )
    finally:
        if restarted_runtime_process is not None and restarted_runtime_process.poll() is None:
            restarted_runtime_process.terminate()
            try:
                restarted_runtime_process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                restarted_runtime_process.kill()
                restarted_runtime_process.wait(timeout=5)
        if restarted_runtime_log_thread is not None:
            restarted_runtime_log_thread.join(timeout=2)