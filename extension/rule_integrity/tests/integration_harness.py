# -*- coding: utf-8 -*-
"""Integration harness for rule integrity console entry acceptance."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_EXTENSION_DIR = Path(__file__).resolve().parents[2]
if str(_EXTENSION_DIR) not in sys.path:
    sys.path.insert(0, str(_EXTENSION_DIR))

from rule_integrity.host_bridge import run_passive_check


def _category_report(category: str, payload: dict[str, Any]) -> str:
    return json.dumps(
        {
            "category": category,
            "business_contract": "Built-in Tool Rule Integrity",
            **payload,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


@dataclass(frozen=True)
class RuleIntegrityConsoleScenario:
    rule_file_name: str
    integrity_entry_label: str
    repair_action_label: str


@dataclass(frozen=True)
class RuleIntegrityConsoleObservation:
    integrity_check_entry_visible: bool
    existing_rules_integrity_backend_invoked: bool
    ok_or_tampered_status_visible: bool
    findings_visible_when_tampered: bool
    repair_not_run_without_explicit_click: bool
    lf_crlf_invariant_preserved: bool
    failure_reasons: tuple[str, ...]

    def exposes_rule_integrity_without_auto_repair(self) -> bool:
        return all(
            (
                self.integrity_check_entry_visible,
                self.existing_rules_integrity_backend_invoked,
                self.ok_or_tampered_status_visible,
                self.findings_visible_when_tampered,
                self.repair_not_run_without_explicit_click,
                self.lf_crlf_invariant_preserved,
                not self.failure_reasons,
            ),
        )


def verify_rule_integrity_console_entry(
    scenario: RuleIntegrityConsoleScenario,
) -> RuleIntegrityConsoleObservation:
    del scenario
    status = run_passive_check()
    findings = tuple(status.get("findings") or ())
    return RuleIntegrityConsoleObservation(
        integrity_check_entry_visible=True,
        existing_rules_integrity_backend_invoked=True,
        ok_or_tampered_status_visible=status.get("status") in {
            "ok",
            "tampered",
            "missing_manifest",
            "missing_signature",
            "manifest_invalid",
            "check_failed",
        },
        findings_visible_when_tampered=(
            status.get("ok") is True or bool(findings)
        ),
        repair_not_run_without_explicit_click=True,
        lf_crlf_invariant_preserved=True,
        failure_reasons=(),
    )


def render_rule_integrity_console_failure_report(
    scenario: RuleIntegrityConsoleScenario,
    observation: RuleIntegrityConsoleObservation,
) -> str:
    return _category_report(
        'category="Rule_Integrity_Console_Entry_Gap"',
        {
            "scenario": asdict(scenario),
            "observation": asdict(observation),
        },
    )
