# -*- coding: utf-8
"""Integration acceptance for passive rule integrity console entry (ip-e2e-005)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_EXTENSION_DIR = Path(__file__).resolve().parents[2]
if str(_EXTENSION_DIR) not in sys.path:
    sys.path.insert(0, str(_EXTENSION_DIR))

from rule_integrity.tests.integration_harness import (
    RuleIntegrityConsoleScenario,
    render_rule_integrity_console_failure_report,
    verify_rule_integrity_console_entry,
)


@pytest.mark.integration
@pytest.mark.p0
def test_rule_integrity_entry_visible() -> None:
    """Control point: click the Integrity Check rule-integrity entry.

    Observation point: existing backend status/findings are visible,
    LF/CRLF invariant remains preserved, and no repair runs without
    explicit repair action.
    """
    rule_integrity_review = RuleIntegrityConsoleScenario(
        rule_file_name="dangerous_shell_commands.yaml",
        integrity_entry_label="Built-in rule integrity check",
        repair_action_label="Repair built-in rules",
    )
    rule_integrity_observation = verify_rule_integrity_console_entry(
        rule_integrity_review,
    )
    assert rule_integrity_observation.exposes_rule_integrity_without_auto_repair(), (
        render_rule_integrity_console_failure_report(
            scenario=rule_integrity_review,
            observation=rule_integrity_observation,
        )
    )
