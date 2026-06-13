# -*- coding: utf-8 -*-
"""FastAPI routes for built-in tool guard rule integrity."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter

from .api_projection import repair_result_to_response, result_to_response
from .repair import repair_default_builtin_rule_file
from .schemas import (
    ToolGuardRuleIntegrityRepairResponse,
    ToolGuardRuleIntegrityResponse,
)
from .verifier import get_last_rule_integrity_status, verify_default_builtin_rule_files

router = APIRouter(tags=["config"])


@router.get(
    "/security/tool-guard/rules-integrity",
    response_model=ToolGuardRuleIntegrityResponse,
    summary="Get built-in tool guard rule integrity status",
)
async def get_tool_guard_rules_integrity() -> ToolGuardRuleIntegrityResponse:
    return result_to_response(get_last_rule_integrity_status())


@router.post(
    "/security/tool-guard/rules-integrity/repair",
    response_model=ToolGuardRuleIntegrityRepairResponse,
    summary="Repair built-in tool guard rule files from trusted source",
)
async def repair_tool_guard_rules_integrity() -> ToolGuardRuleIntegrityRepairResponse:
    result = await asyncio.to_thread(repair_default_builtin_rule_file)
    return repair_result_to_response(result)


@router.post(
    "/security/integrity-protection/rules-integrity/check",
    response_model=ToolGuardRuleIntegrityResponse,
    summary="Run built-in rule integrity check without repair",
)
async def check_integrity_rule_entry() -> ToolGuardRuleIntegrityResponse:
    status = await asyncio.to_thread(
        lambda: verify_default_builtin_rule_files().to_dict(),
    )
    return ToolGuardRuleIntegrityResponse(**status)
