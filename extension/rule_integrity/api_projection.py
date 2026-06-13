# -*- coding: utf-8 -*-
"""Map rule integrity domain results to API response models."""
from __future__ import annotations

from .models import RuleIntegrityRepairResult, RuleIntegrityResult
from .schemas import (
    ToolGuardRuleIntegrityFindingResponse,
    ToolGuardRuleIntegrityRepairResponse,
    ToolGuardRuleIntegrityResponse,
)


def result_to_response(status: RuleIntegrityResult) -> ToolGuardRuleIntegrityResponse:
    return ToolGuardRuleIntegrityResponse(
        ok=status.ok,
        status=status.status,
        message=status.message,
        checked_at=status.checked_at,
        findings=[
            ToolGuardRuleIntegrityFindingResponse(**finding.to_dict())
            for finding in status.findings
        ],
    )


def repair_result_to_response(
    result: RuleIntegrityRepairResult,
) -> ToolGuardRuleIntegrityRepairResponse:
    return ToolGuardRuleIntegrityRepairResponse(
        ok=result.ok,
        message=result.message,
        source_url=result.source_url,
        backup_path=result.backup_path,
        integrity=result_to_response(result.integrity),
    )
