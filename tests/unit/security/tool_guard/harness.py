# -*- coding: utf-8 -*-
"""Business-readable harness for built-in tool guard rule integrity acceptance."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qwenpaw.security.tool_guard.rules_integrity import (
    DANGEROUS_SHELL_RULES_NAME,
    MANIFEST_NAME,
    SIGNATURE_NAME,
    RuleIntegrityResult,
    get_last_rule_integrity_status,
    verify_builtin_rule_files,
)

_OFFICIAL_RULES_DIR = (
    Path(__file__).resolve().parents[4]
    / "src"
    / "qwenpaw"
    / "security"
    / "tool_guard"
    / "rules"
)
_OFFICIAL_MANIFEST_SHA256 = (
    "138904e36b497e300ab93722db569f454c55a02ae1d08726034603695b4624f8"
)
_REQUIRED_DANGEROUS_RM_RULE_ID = "TOOL_CMD_DANGEROUS_RM"


@dataclass(frozen=True)
class SignedManifestBundle:
    """Official signed manifest artifacts reused across line-ending branches."""

    manifest_bytes: bytes
    signature_text: str


class ToolGuardRulesIntegrityHarness:
    """Harness abstraction for sec-e2e-029 built-in rule line-ending invariance."""

    def __init__(self, temporary_rules_directory: Path) -> None:
        self._temporary_rules_directory = temporary_rules_directory

    @classmethod
    def for_temporary_rules_directory(cls, temporary_rules_directory: Path) -> ToolGuardRulesIntegrityHarness:
        return cls(temporary_rules_directory)

    @classmethod
    def for_contract_probe(cls) -> ToolGuardRulesIntegrityHarness:
        probe_directory = _OFFICIAL_RULES_DIR.parent / ".contract_probe_unused"
        probe_directory.mkdir(parents=True, exist_ok=True)
        return cls(probe_directory)

    @property
    def official_manifest_sha256(self) -> str:
        return _OFFICIAL_MANIFEST_SHA256

    def load_official_lf_canonical_rule_content(self) -> bytes:
        raw_rule_bytes = (_OFFICIAL_RULES_DIR / DANGEROUS_SHELL_RULES_NAME).read_bytes()
        return self._normalize_line_endings_to_lf(raw_rule_bytes)

    def load_official_signed_manifest_bundle(self) -> SignedManifestBundle:
        manifest_bytes = (_OFFICIAL_RULES_DIR / MANIFEST_NAME).read_bytes()
        signature_text = (_OFFICIAL_RULES_DIR / SIGNATURE_NAME).read_text(encoding="ascii")
        return SignedManifestBundle(
            manifest_bytes=manifest_bytes,
            signature_text=signature_text,
        )

    def transform_to_crlf_only_line_endings(self, lf_canonical_rule_content: bytes) -> bytes:
        normalized_lf_content = self._normalize_line_endings_to_lf(lf_canonical_rule_content)
        return normalized_lf_content.replace(b"\n", b"\r\n")

    def remove_required_dangerous_rm_rule(self, lf_canonical_rule_content: bytes) -> bytes:
        normalized_lf_content = self._normalize_line_endings_to_lf(lf_canonical_rule_content)
        rule_text = normalized_lf_content.decode("utf-8")
        marker = f"- id: {_REQUIRED_DANGEROUS_RM_RULE_ID}"
        marker_index = rule_text.find(marker)
        if marker_index < 0:
            raise ValueError(
                f"required semantic tamper anchor {_REQUIRED_DANGEROUS_RM_RULE_ID} is missing",
            )

        next_rule_index = rule_text.find("\n- id:", marker_index + len(marker))
        if next_rule_index < 0:
            weakened_rule_text = rule_text[:marker_index].rstrip() + "\n"
        else:
            weakened_rule_text = rule_text[:marker_index] + rule_text[next_rule_index + 1 :]
        return weakened_rule_text.encode("utf-8")

    def stage_signed_rules_bundle(
        self,
        *,
        rule_content: bytes,
        signed_manifest_bundle: SignedManifestBundle,
    ) -> None:
        if self._temporary_rules_directory.exists():
            shutil.rmtree(self._temporary_rules_directory)
        self._temporary_rules_directory.mkdir(parents=True, exist_ok=True)

        (self._temporary_rules_directory / DANGEROUS_SHELL_RULES_NAME).write_bytes(rule_content)
        (self._temporary_rules_directory / MANIFEST_NAME).write_bytes(
            signed_manifest_bundle.manifest_bytes,
        )
        (self._temporary_rules_directory / SIGNATURE_NAME).write_text(
            signed_manifest_bundle.signature_text,
            encoding="ascii",
        )

    def verify_builtin_rules(self) -> RuleIntegrityResult:
        return verify_builtin_rule_files(
            self._temporary_rules_directory,
            [DANGEROUS_SHELL_RULES_NAME],
        )

    def read_cached_integrity_status(self) -> RuleIntegrityResult:
        return get_last_rule_integrity_status()

    def sha256_normalized_content(self, content_bytes: bytes) -> str:
        from qwenpaw.security.tool_guard.rules_integrity import _sha256_normalized_content

        return _sha256_normalized_content(content_bytes)

    def sha256_normalized_content_via_manifest_script(self, content_bytes: bytes) -> str:
        import importlib.util

        script_path = _OFFICIAL_RULES_DIR.parents[4] / "scripts" / "update_tool_rule_manifest.py"
        module_spec = importlib.util.spec_from_file_location(
            "update_tool_rule_manifest",
            script_path,
        )
        if module_spec is None or module_spec.loader is None:
            raise ImportError(f"unable to load manifest script at {script_path}")
        manifest_script = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(manifest_script)
        normalized_hasher = manifest_script._sha256_normalized_content
        return normalized_hasher(content_bytes)

    def expect_integrity_ok(
        self,
        verification_result: RuleIntegrityResult,
        cached_status: RuleIntegrityResult,
        *,
        branch_label: str,
    ) -> None:
        if not verification_result.ok or verification_result.status != "ok":
            raise AssertionError(
                self.render_line_ending_invariant_failure_report(
                    category="Line_Ending_Invariant_Gap",
                    branch_label=branch_label,
                    detail=(
                        "expected ok=true with status ok, "
                        f"observed ok={verification_result.ok} status={verification_result.status} "
                        f"findings={self._findings_summary(verification_result)}"
                    ),
                ),
            )

        if not cached_status.ok or cached_status.status != "ok":
            raise AssertionError(
                self.render_line_ending_invariant_failure_report(
                    category="Rules_Integrity_Status_Projection_Gap",
                    branch_label=branch_label,
                    detail=(
                        "cached rules-integrity status must project ok=true with status ok, "
                        f"observed ok={cached_status.ok} status={cached_status.status}"
                    ),
                ),
            )

    def expect_integrity_tampered(
        self,
        verification_result: RuleIntegrityResult,
        cached_status: RuleIntegrityResult,
        *,
        branch_label: str,
    ) -> None:
        if verification_result.ok or verification_result.status != "tampered":
            raise AssertionError(
                self.render_line_ending_invariant_failure_report(
                    category="Semantic_Tamper_Detection_Gap",
                    branch_label=branch_label,
                    detail=(
                        "expected ok=false with status tampered, "
                        f"observed ok={verification_result.ok} status={verification_result.status}"
                    ),
                ),
            )

        mismatch_findings = [
            finding
            for finding in verification_result.findings
            if finding.reason == "sha256_mismatch"
        ]
        if not mismatch_findings:
            raise AssertionError(
                self.render_line_ending_invariant_failure_report(
                    category="Semantic_Tamper_Detection_Gap",
                    branch_label=branch_label,
                    detail="expected sha256_mismatch finding for semantic tamper branch",
                ),
            )

        if cached_status.ok or cached_status.status != "tampered":
            raise AssertionError(
                self.render_line_ending_invariant_failure_report(
                    category="Rules_Integrity_Status_Projection_Gap",
                    branch_label=branch_label,
                    detail=(
                        "cached rules-integrity status must project tampered after semantic tamper, "
                        f"observed ok={cached_status.ok} status={cached_status.status}"
                    ),
                ),
            )

    def expect_same_normalized_digest(self, *normalized_digests: str) -> None:
        unique_digests = set(normalized_digests)
        if len(unique_digests) != 1:
            raise AssertionError(
                self.render_line_ending_invariant_failure_report(
                    category="Normalized_Content_Hash_Drift",
                    branch_label="shared_helper_contract",
                    detail=f"LF, CRLF, and lone-CR variants must hash identically, observed={sorted(unique_digests)}",
                ),
            )

    def expect_digest_matches_manifest_baseline(
        self,
        normalized_digest: str,
        manifest_baseline_digest: str,
    ) -> None:
        if normalized_digest != manifest_baseline_digest:
            raise AssertionError(
                self.render_line_ending_invariant_failure_report(
                    category="Manifest_Baseline_Digest_Mismatch",
                    branch_label="shared_helper_contract",
                    detail=(
                        "official LF-canonical rule content must match signed manifest baseline, "
                        f"expected={manifest_baseline_digest} observed={normalized_digest}"
                    ),
                ),
            )

    def expect_manifest_script_uses_same_helper(
        self,
        manifest_script_digest: str,
        runtime_helper_digest: str,
    ) -> None:
        if manifest_script_digest != runtime_helper_digest:
            raise AssertionError(
                self.render_line_ending_invariant_failure_report(
                    category="Manifest_Runtime_Hash_Drift",
                    branch_label="shared_helper_contract",
                    detail=(
                        "manifest generation and runtime verify must share _sha256_normalized_content, "
                        f"runtime={runtime_helper_digest} manifest_script={manifest_script_digest}"
                    ),
                ),
            )

    @staticmethod
    def render_line_ending_invariant_failure_report(
        *,
        category: str,
        branch_label: str,
        detail: str,
    ) -> str:
        return (
            f'category="{category}" '
            f'branch="{branch_label}" '
            f"detail={detail}"
        )

    @staticmethod
    def _normalize_line_endings_to_lf(content_bytes: bytes) -> bytes:
        return content_bytes.replace(b"\r\n", b"\n").replace(b"\r", b"\n")

    @staticmethod
    def _findings_summary(verification_result: RuleIntegrityResult) -> list[dict[str, Any]]:
        return [finding.to_dict() for finding in verification_result.findings]
