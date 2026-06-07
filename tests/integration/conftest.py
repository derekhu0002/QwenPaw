# -*- coding: utf-8 -*-
"""Shared fixtures for integration tests.

These fixtures start a real QwenPaw app subprocess with isolated workspace
directories and a sanitized environment to avoid touching local secrets.

Subprocess coverage (optional):

    QWENPAW_INTEGRATION_COVERAGE=1 pytest tests/integration/

When set, ``pytest_sessionstart`` writes a coverage rcfile under
``.integration_coverage/`` with an **absolute** ``source=`` path
(``…/src/qwenpaw``); the app subprocess runs with
``COVERAGE_PROCESS_START`` / ``COVERAGE_FILE`` so the child traces
that tree. The fixture stops the app with **SIGINT** first so coverage
can flush (SIGTERM often yields empty data). After the session, files
under ``.integration_coverage/`` are combined and HTML is written to
``htmlcov-integration/``. Run integration tests without ``--cov`` from
pytest-cov (or use ``--no-cov``) so the parent process does not enforce
``fail_under`` on near-zero host-process coverage. This flow is not
validated under ``pytest-xdist``.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest

_INTEGRATION_COVERAGE_DIR: Path | None = None
_COVERAGE_SUBPROC_BASENAME = "integration_subproc"
_COVERAGE_RCFILE_NAME = "coverage_subprocess.ini"


def _write_integration_subprocess_rc(root: Path, dest_ini: Path) -> None:
    """Write a coverage rcfile with absolute ``source`` for the app subprocess.

    Relative ``source=`` paths in a checked-in rcfile are not resolved reliably
    when the file is loaded via ``COVERAGE_PROCESS_START``, which produced
    empty traces (0 files) even though the app ran.
    """
    src_qwenpaw = (root / "src" / "qwenpaw").resolve()
    text = (
        "[run]\n"
        "parallel = true\n"
        "branch = false\n"
        f"source = {src_qwenpaw}\n"
        "omit =\n"
        "    */tests/*\n"
        "    */test_*\n"
        "    */__pycache__/*\n"
    )
    dest_ini.write_text(text, encoding="utf-8")


def _integration_coverage_requested() -> bool:
    return os.environ.get(
        "QWENPAW_INTEGRATION_COVERAGE",
        "",
    ).strip().lower() in (
        "1",
        "true",
        "yes",
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    """Prepare directory and config for subprocess coverage when requested."""
    global _INTEGRATION_COVERAGE_DIR
    if not _integration_coverage_requested():
        return
    root = Path(session.config.rootpath).resolve()
    _INTEGRATION_COVERAGE_DIR = root / ".integration_coverage"
    _INTEGRATION_COVERAGE_DIR.mkdir(parents=True, exist_ok=True)
    for p in _INTEGRATION_COVERAGE_DIR.glob(f"{_COVERAGE_SUBPROC_BASENAME}*"):
        p.unlink(missing_ok=True)
    _write_integration_subprocess_rc(
        root,
        _INTEGRATION_COVERAGE_DIR / _COVERAGE_RCFILE_NAME,
    )


def pytest_sessionfinish(  # pylint: disable=unused-argument
    session: pytest.Session,
    exitstatus: int,
) -> None:
    """Merge parallel coverage files from app subprocesses and write HTML."""
    if (
        not _integration_coverage_requested()
        or _INTEGRATION_COVERAGE_DIR is None
    ):
        return
    wd = _INTEGRATION_COVERAGE_DIR
    if not any(wd.glob(f"{_COVERAGE_SUBPROC_BASENAME}*")):
        print(
            "[integration coverage] No data files under "
            f"{wd} (no app_server tests ran?).",
            flush=True,
        )
        return

    combine = subprocess.run(
        [
            sys.executable,
            "-m",
            "coverage",
            "combine",
            "--data-file",
            _COVERAGE_SUBPROC_BASENAME,
        ],
        cwd=wd,
        capture_output=True,
        text=True,
        check=False,
    )
    if combine.returncode != 0:
        print(
            "[integration coverage] coverage combine failed:\n"
            f"{combine.stdout}\n{combine.stderr}",
            flush=True,
        )
        return

    root = Path(session.config.rootpath).resolve()
    html_dir = root / "htmlcov-integration"
    if html_dir.is_dir():
        shutil.rmtree(html_dir)
    html = subprocess.run(
        [
            sys.executable,
            "-m",
            "coverage",
            "html",
            "--data-file",
            _COVERAGE_SUBPROC_BASENAME,
            "-d",
            str(html_dir),
        ],
        cwd=wd,
        capture_output=True,
        text=True,
        check=False,
    )
    if html.returncode != 0:
        print(
            "[integration coverage] coverage html failed:\n"
            f"{html.stdout}\n{html.stderr}",
            flush=True,
        )
        return

    print(
        f"[integration coverage] HTML report: {html_dir / 'index.html'}",
        flush=True,
    )


_SENSITIVE_ENV_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DASHSCOPE_API_KEY",
    "DINGTALK_APP_KEY",
    "DINGTALK_APP_SECRET",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "DISCORD_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
)


def _find_free_port(host: str = "127.0.0.1") -> int:
    """Bind to port 0 and return the assigned free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _wait_for_http_ready(
    client: httpx.Client,
    *,
    url: str,
    ready_statuses: set[int],
    timeout_seconds: float,
    process: subprocess.Popen[str],
    logs: list[str],
    service_name: str,
) -> str | None:
    start_at = time.time()
    last_error: str | None = None
    while time.time() - start_at < timeout_seconds:
        if process.poll() is not None:
            return (
                f"{service_name} exited during startup.\n"
                f"exit_code={process.returncode}\n"
                f"logs:\n{''.join(logs)[-4000:]}"
            )
        try:
            response = client.get(url)
            if response.status_code in ready_statuses:
                return None
            last_error = f"unexpected status {response.status_code}"
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            last_error = str(exc)
        time.sleep(0.25)
    return (
        f"{service_name} did not become ready in time.\n"
        f"last_error={last_error}\n"
        f"logs:\n{''.join(logs)[-4000:]}"
    )


def _wait_for_log_marker(
    *,
    marker: str,
    timeout_seconds: float,
    process: subprocess.Popen[str],
    logs: list[str],
    service_name: str,
) -> str | None:
    start_at = time.time()
    while time.time() - start_at < timeout_seconds:
        if any(marker in line for line in logs):
            return None
        if process.poll() is not None:
            return (
                f"{service_name} exited during startup.\n"
                f"exit_code={process.returncode}\n"
                f"logs:\n{''.join(logs)[-4000:]}"
            )
        time.sleep(0.25)
    return (
        f"{service_name} did not emit startup marker '{marker}' in time.\n"
        f"logs:\n{''.join(logs)[-4000:]}"
    )


def _tee_stream(stream, buffer: list[str]) -> None:
    """Read subprocess output, tag and print live, keep a raw copy."""
    prefix = "[app server] "
    try:
        for line in iter(stream.readline, ""):
            buffer.append(line)
            try:
                print(f"{prefix}{line}", end="", flush=True)
            except (OSError, ValueError):
                # pytest may close captured stdout before this daemon thread
                # finishes draining; keep the raw copy in `buffer` regardless.
                pass
    finally:
        stream.close()


@dataclass
class AppServer:
    """Handle to a running app subprocess used by tests."""

    host: str
    port: int
    process: subprocess.Popen[str]
    client: httpx.Client
    logs: list[str]
    log_thread: threading.Thread
    # Working directory of the subprocess (= QWENPAW_WORKING_DIR). Tests that
    # need to seed file-backed stores (inbox_events.json, cron jobs_history/,
    # backups, etc.) write directly under this path. The subprocess re-reads
    # these files on each HTTP request, so no restart is needed after seeding.
    working_dir: Path
    security_center_data_dir: Path | None = None
    startup_error: str | None = None
    security_center_api_url: str | None = None
    security_center_web_url: str | None = None
    security_center_api_process: subprocess.Popen[str] | None = None
    security_center_web_process: subprocess.Popen[str] | None = None
    security_center_api_logs: list[str] | None = None
    security_center_web_logs: list[str] | None = None
    security_center_api_log_thread: threading.Thread | None = None
    security_center_web_log_thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def logs_tail(self, chars: int = 4000) -> str:
        return "".join(self.logs)[-chars:]

    @staticmethod
    def _compact(value: Any, max_len: int | None = None) -> str:
        """Render params/body/response for logs (single line, escaped).

        ``max_len`` is only applied when set; by default the full string
        is kept so integration logs are usable for debugging.
        """
        if value is None:
            return "-"
        if isinstance(value, str):
            text = value
        else:
            try:
                text = json.dumps(value, ensure_ascii=False, sort_keys=True)
            except TypeError:
                text = repr(value)
        text = text.replace("\n", "\\n")
        if max_len is not None and len(text) > max_len:
            return f"{text[: max_len - 3]}..."
        return text

    def api_request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send a request and print the full request/response to stdout."""
        if self.startup_error is not None:
            raise AssertionError(self.startup_error)
        url = f"{self.base_url}{path}" if path.startswith("/") else path
        request_payload = kwargs.get("json")
        if request_payload is None:
            request_payload = kwargs.get("data")
        request_params = kwargs.get("params")

        response = self.client.request(
            method=method.upper(),
            url=url,
            **kwargs,
        )
        response_text = response.text

        level = "PASS" if 200 <= response.status_code < 400 else "FAIL"
        print(
            (
                f"[integration][{level}] {method.upper()} {path} | "
                f"params={self._compact(request_params)} | "
                f"request={self._compact(request_payload)} | "
                f"status={response.status_code} | "
                f"response={self._compact(response_text)}"
            ),
            flush=True,
        )
        return response


@pytest.fixture(scope="module")
def app_server(  # pylint: disable=too-many-statements,too-many-branches
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[AppServer]:
    """Start one isolated qwenpaw app process per test module.

    Module-scoped: cases in the same file share one subprocess. Cross-module
    isolation is preserved by re-launching with a fresh tmp dir. Cases must
    use unique resource ids (agent_id, chat_id, ...) to stay isolated within
    a module — current convention (e.g. ``integ_ws_01``) already supports this.
    """
    tmp_path = tmp_path_factory.mktemp("app_server")
    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src"
    host = "127.0.0.1"
    port = _find_free_port(host)

    working_dir = tmp_path / "working"
    secret_dir = tmp_path / "working.secret"
    backups_dir = tmp_path / "working.backups"
    working_dir.mkdir(parents=True, exist_ok=True)
    secret_dir.mkdir(parents=True, exist_ok=True)
    backups_dir.mkdir(parents=True, exist_ok=True)
    security_center_data_dir = tmp_path / "security-center-data"
    security_center_data_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    for key in _SENSITIVE_ENV_VARS:
        env.pop(key, None)

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
    # Force UTF-8 stdio in the subprocess so non-ASCII log lines (e.g.
    # 中文/emoji from skills, agentscope, etc.) don't crash the parent's
    # _tee_stream reader on Windows where the default console encoding
    # is cp1252.
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

    if _integration_coverage_requested():
        if _INTEGRATION_COVERAGE_DIR is None:
            raise AssertionError(
                "QWENPAW_INTEGRATION_COVERAGE is set but coverage dir was not "
                "initialised (pytest_sessionstart should create "
                ".integration_coverage/).",
            )
        rcfile = _INTEGRATION_COVERAGE_DIR / _COVERAGE_RCFILE_NAME
        env["COVERAGE_PROCESS_START"] = str(rcfile.resolve())
        env["COVERAGE_FILE"] = str(
            _INTEGRATION_COVERAGE_DIR / _COVERAGE_SUBPROC_BASENAME,
        )

    logs: list[str] = []
    security_center_api_logs: list[str] = []
    security_center_web_logs: list[str] = []
    with subprocess.Popen(
        [sys.executable, "-m", "deploy.api.app"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
        env=security_center_env,
        cwd=repo_root,
    ) as security_center_api_process, subprocess.Popen(
        [sys.executable, "-m", "deploy.web.server"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
        env=security_center_web_env,
        cwd=repo_root,
    ) as security_center_web_process, subprocess.Popen(
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
        # Decode subprocess output as UTF-8 in the parent. Without this,
        # Popen falls back to locale.getpreferredencoding(False) which
        # is cp1252 on Windows CI runners and crashes _tee_stream.
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=repo_root,
    ) as process:
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

        # 15s default lets cold-start endpoints (ACP getter, heartbeat)
        # finish without hiding real deadlocks; 30s in coverage mode
        # for tracer overhead.
        http_timeout = 30.0 if _integration_coverage_requested() else 15.0
        client = httpx.Client(timeout=http_timeout, trust_env=False)

        try:
            max_wait_seconds = 60
            start_at = time.time()
            last_error: str | None = None
            startup_error: str | None = None

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

            while time.time() - start_at < max_wait_seconds:
                if startup_error is not None:
                    break
                if process.poll() is not None:
                    startup_error = (
                        "qwenpaw app exited during startup.\n"
                        f"exit_code={process.returncode}\n"
                        f"logs:\n{''.join(logs)[-4000:]}"
                    )
                    break

                try:
                    resp = client.get(f"http://{host}:{port}/api/version")
                    if resp.status_code == 200:
                        # /api/version turns green before background startup
                        # consistently finishes under cold boot. Wait for the
                        # runtime marker instead of using a fixed sleep so the
                        # security integration slice does not race startup.
                        startup_error = _wait_for_log_marker(
                            marker="Background startup completed",
                            timeout_seconds=20.0,
                            process=process,
                            logs=logs,
                            service_name="qwenpaw app",
                        )
                        break
                except (httpx.ConnectError, httpx.TimeoutException) as exc:
                    last_error = str(exc)
                time.sleep(0.5)
            else:
                startup_error = (
                    "qwenpaw app did not become ready in time.\n"
                    f"last_error={last_error}\n"
                    f"logs:\n{''.join(logs)[-4000:]}"
                )

            yield AppServer(
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
        finally:
            client.close()
            if process.poll() is None:
                # On POSIX, SIGINT lets uvicorn shut down cleanly so
                # subprocess coverage data flushes (SIGTERM often skips
                # atexit / data-file write). On Windows, SIGINT is not
                # delivered reliably to subprocesses (CTRL_C_EVENT only
                # works for console process groups created with
                # CREATE_NEW_PROCESS_GROUP), so use terminate directly.
                # Windows CI does not enable subprocess coverage, so the
                # graceful-shutdown nicety isn't needed there.
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
