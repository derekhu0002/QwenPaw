# -*- coding: utf-8 -*-
"""Host wiring for built-in tool guard rule integrity."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import (
    DANGEROUS_SHELL_RULES_NAME,
    HASH_SCHEME,
    MANIFEST_NAME,
    RECOVERY_SOURCE_URL,
    SIGNATURE_NAME,
    SIGNATURE_SCHEME,
)
from .models import (
    RuleIntegrityFinding,
    RuleIntegrityRepairResult,
    RuleIntegrityResult,
)
from .repair import repair_default_builtin_rule_file
from .verifier import (
    get_last_rule_integrity_status,
    sha256_normalized_content,
    verify_builtin_rule_files,
    verify_default_builtin_rule_files,
)


def run_passive_check() -> dict[str, Any]:
    """Run passive rule integrity check for Integrity Protection delivery."""

    return verify_default_builtin_rule_files().to_dict()


def get_router():
    """Return the FastAPI router for rule integrity delivery routes."""

    from .routes import router

    return router


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
    "get_last_rule_integrity_status",
    "repair_default_builtin_rule_file",
    "run_passive_check",
    "get_router",
    "sha256_normalized_content",
    "verify_builtin_rule_files",
    "verify_default_builtin_rule_files",
]
