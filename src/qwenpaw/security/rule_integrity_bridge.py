# -*- coding: utf-8 -*-
"""Thin bridge from qwenpaw core into extension/rule_integrity."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXTENSION_DIR = _REPO_ROOT / "extension"
if str(_EXTENSION_DIR) not in sys.path:
    sys.path.insert(0, str(_EXTENSION_DIR))

from rule_integrity.host_bridge import (  # noqa: E402
    DANGEROUS_SHELL_RULES_NAME,
    HASH_SCHEME,
    MANIFEST_NAME,
    RECOVERY_SOURCE_URL,
    SIGNATURE_NAME,
    SIGNATURE_SCHEME,
    RuleIntegrityFinding,
    RuleIntegrityRepairResult,
    RuleIntegrityResult,
    get_last_rule_integrity_status,
    get_router,
    repair_default_builtin_rule_file,
    run_passive_check,
    sha256_normalized_content,
    verify_builtin_rule_files,
    verify_default_builtin_rule_files,
)
from rule_integrity.schemas import (  # noqa: E402
    ToolGuardRuleIntegrityFindingResponse,
    ToolGuardRuleIntegrityRepairResponse,
    ToolGuardRuleIntegrityResponse,
)
from rule_integrity.startup import periodic_rule_integrity_check  # noqa: E402

# Backward-compatible alias used by release tooling and frozen tests.
_sha256_normalized_content = sha256_normalized_content


def get_rule_integrity_router():
    """Return the FastAPI router owned by extension/rule_integrity."""

    return get_router()


__all__ = [
    "DANGEROUS_SHELL_RULES_NAME",
    "HASH_SCHEME",
    "MANIFEST_NAME",
    "RECOVERY_SOURCE_URL",
    "SIGNATURE_NAME",
    "SIGNATURE_SCHEME",
    "RuleIntegrityFinding",
    "RuleIntegrityRepairResult",
    "RuleIntegrityResult",
    "ToolGuardRuleIntegrityFindingResponse",
    "ToolGuardRuleIntegrityRepairResponse",
    "ToolGuardRuleIntegrityResponse",
    "_sha256_normalized_content",
    "get_last_rule_integrity_status",
    "get_router",
    "get_rule_integrity_router",
    "periodic_rule_integrity_check",
    "repair_default_builtin_rule_file",
    "run_passive_check",
    "sha256_normalized_content",
    "verify_builtin_rule_files",
    "verify_default_builtin_rule_files",
]
