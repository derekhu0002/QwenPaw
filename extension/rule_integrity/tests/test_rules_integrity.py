# -*- coding: utf-8 -*-
"""Frozen explicit and critical guard tests for built-in tool rule integrity."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_EXTENSION_DIR = Path(__file__).resolve().parents[2]
if str(_EXTENSION_DIR) not in sys.path:
    sys.path.insert(0, str(_EXTENSION_DIR))

from rule_integrity.tests.harness import ToolGuardRulesIntegrityHarness


@pytest.fixture
def rules_integrity_harness(tmp_path: Path) -> ToolGuardRulesIntegrityHarness:
    return ToolGuardRulesIntegrityHarness.for_temporary_rules_directory(tmp_path / "signed_rules")


def test_builtin_rule_line_ending_invariant(rules_integrity_harness: ToolGuardRulesIntegrityHarness) -> None:
    # GIVEN
    official_lf_canonical_rule_content = rules_integrity_harness.load_official_lf_canonical_rule_content()
    official_signed_manifest_bundle = rules_integrity_harness.load_official_signed_manifest_bundle()
    crlf_only_rule_content = rules_integrity_harness.transform_to_crlf_only_line_endings(
        official_lf_canonical_rule_content,
    )
    semantic_tampered_rule_content = rules_integrity_harness.remove_required_dangerous_rm_rule(
        official_lf_canonical_rule_content,
    )

    # WHEN
    rules_integrity_harness.stage_signed_rules_bundle(
        rule_content=official_lf_canonical_rule_content,
        signed_manifest_bundle=official_signed_manifest_bundle,
    )
    lf_canonical_verification = rules_integrity_harness.verify_builtin_rules()
    lf_canonical_cached_status = rules_integrity_harness.read_cached_integrity_status()

    rules_integrity_harness.stage_signed_rules_bundle(
        rule_content=crlf_only_rule_content,
        signed_manifest_bundle=official_signed_manifest_bundle,
    )
    crlf_only_verification = rules_integrity_harness.verify_builtin_rules()
    crlf_only_cached_status = rules_integrity_harness.read_cached_integrity_status()

    rules_integrity_harness.stage_signed_rules_bundle(
        rule_content=semantic_tampered_rule_content,
        signed_manifest_bundle=official_signed_manifest_bundle,
    )
    semantic_tamper_verification = rules_integrity_harness.verify_builtin_rules()
    semantic_tamper_cached_status = rules_integrity_harness.read_cached_integrity_status()

    # THEN
    rules_integrity_harness.expect_integrity_ok(
        lf_canonical_verification,
        lf_canonical_cached_status,
        branch_label="LF_canonical",
    )
    rules_integrity_harness.expect_integrity_ok(
        crlf_only_verification,
        crlf_only_cached_status,
        branch_label="CRLF_only",
    )
    rules_integrity_harness.expect_integrity_tampered(
        semantic_tamper_verification,
        semantic_tamper_cached_status,
        branch_label="semantic_tamper",
    )


def test_sha256_normalized_content_shared_helper_contract() -> None:
    # GIVEN
    contract_probe = ToolGuardRulesIntegrityHarness.for_contract_probe()
    lf_canonical_sample = b"official rule line one\nofficial rule line two\n"
    crlf_only_sample = b"official rule line one\r\nofficial rule line two\r\n"
    lone_cr_sample = b"official rule line one\rofficial rule line two\r"
    official_lf_canonical_rule_content = contract_probe.load_official_lf_canonical_rule_content()
    official_manifest_sha256 = contract_probe.official_manifest_sha256

    # WHEN
    lf_canonical_digest = contract_probe.sha256_normalized_content(lf_canonical_sample)
    crlf_only_digest = contract_probe.sha256_normalized_content(crlf_only_sample)
    lone_cr_digest = contract_probe.sha256_normalized_content(lone_cr_sample)
    official_rule_digest = contract_probe.sha256_normalized_content(official_lf_canonical_rule_content)
    manifest_script_digest = contract_probe.sha256_normalized_content_via_manifest_script(
        official_lf_canonical_rule_content,
    )

    # THEN
    contract_probe.expect_same_normalized_digest(
        lf_canonical_digest,
        crlf_only_digest,
        lone_cr_digest,
    )
    contract_probe.expect_digest_matches_manifest_baseline(
        official_rule_digest,
        official_manifest_sha256,
    )
    contract_probe.expect_manifest_script_uses_same_helper(
        manifest_script_digest,
        official_rule_digest,
    )
