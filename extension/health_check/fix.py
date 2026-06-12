# -*- coding: utf-8 -*-
"""Confirmed Health Check doctor fix execution."""
from __future__ import annotations

from pathlib import Path

from qwenpaw.cli.doctor_fix_runner import run_doctor_fix
from qwenpaw.security.integrity_protection import HealthCheckFixResult

from .constants import DEFAULT_HEALTH_FIX_ID


def run_confirmed_health_fix(
    *,
    selected_repair: str,
    confirmation_phrase: str,
    expected_confirmation_phrase: str,
    working_dir: Path | None = None,
) -> HealthCheckFixResult:
    """Run one selected doctor fix only after an explicit confirmation."""

    if confirmation_phrase != expected_confirmation_phrase:
        return HealthCheckFixResult(
            confirmed=False,
            selected_repair=selected_repair,
            fix_id="",
            executed=False,
            exit_code=1,
            output=("explicit confirmation phrase did not match",),
        )

    fix_id = DEFAULT_HEALTH_FIX_ID
    output: list[str] = []

    def _echo(message: str) -> None:
        output.append(message)

    code = run_doctor_fix(
        dry_run=False,
        yes=True,
        only=fix_id,
        no_backup=False,
        backup_dir=None,
        working_dir=working_dir,
        echo=_echo,
        echo_err=_echo,
        confirm_fn=lambda _message: True,
        argv=["qwenpaw", "doctor", "fix", "--only", fix_id, "--yes"],
        non_interactive=True,
    )
    return HealthCheckFixResult(
        confirmed=True,
        selected_repair=selected_repair,
        fix_id=fix_id,
        executed=True,
        exit_code=code,
        output=tuple(output),
    )
