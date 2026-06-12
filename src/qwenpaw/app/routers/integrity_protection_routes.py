# -*- coding: utf-8 -*-
"""Integrity Protection delivery routes (settings, source trust, health, rule check)."""
from __future__ import annotations

import asyncio
from pathlib import Path as FilePath

from fastapi import APIRouter

from .schemas_integrity_delivery import (
    HealthCheckFixRequest,
    HealthCheckFixResponse,
    HealthCheckScanRequest,
    HealthCheckScanResponse,
    IntegrityProtectionSettingsResponse,
    SourceTrustVerifyRequest,
    SourceTrustVerifyResponse,
    ToolGuardRuleIntegrityResponse,
)

router = APIRouter(tags=["config"])


@router.get(
    "/security/integrity-protection/settings",
    response_model=IntegrityProtectionSettingsResponse,
    summary="Get default-off Integrity Protection settings",
)
async def get_integrity_protection_settings() -> IntegrityProtectionSettingsResponse:
    from ...security.integrity_protection import get_default_integrity_settings

    settings = get_default_integrity_settings()
    return IntegrityProtectionSettingsResponse(**settings.to_dict())


@router.post(
    "/security/integrity-protection/source-trust/verify",
    response_model=SourceTrustVerifyResponse,
    summary="Verify a skill or agent package without installing it",
)
async def verify_integrity_source_trust(
    body: SourceTrustVerifyRequest,
) -> SourceTrustVerifyResponse:
    from ...security.integrity_protection import verify_source_trust_package

    result = await asyncio.to_thread(
        verify_source_trust_package,
        FilePath(body.package_path),
    )
    return SourceTrustVerifyResponse(**result.to_dict())


@router.post(
    "/security/integrity-protection/health-check/scan",
    response_model=HealthCheckScanResponse,
    summary="Run read-only Integrity Protection health check scan",
)
async def run_integrity_health_check_scan(
    body: HealthCheckScanRequest | None = None,
) -> HealthCheckScanResponse:
    from ...security.integrity_protection import run_health_check_scan

    result = await asyncio.to_thread(
        run_health_check_scan,
        deep=bool(body.deep) if body is not None else False,
    )
    return HealthCheckScanResponse(**result.to_dict())


@router.post(
    "/security/integrity-protection/health-check/fix",
    response_model=HealthCheckFixResponse,
    summary="Run one explicitly confirmed doctor fix",
)
async def run_integrity_health_check_fix(
    body: HealthCheckFixRequest,
) -> HealthCheckFixResponse:
    from ...security.integrity_protection import run_confirmed_health_fix

    result = await asyncio.to_thread(
        run_confirmed_health_fix,
        selected_repair=body.selected_repair,
        confirmation_phrase=body.confirmation_phrase,
        expected_confirmation_phrase=body.expected_confirmation_phrase,
    )
    return HealthCheckFixResponse(**result.to_dict())


@router.post(
    "/security/integrity-protection/rules-integrity/check",
    response_model=ToolGuardRuleIntegrityResponse,
    summary="Run built-in rule integrity check without repair",
)
async def check_integrity_rule_entry() -> ToolGuardRuleIntegrityResponse:
    from ...security.integrity_protection import run_rule_integrity_check

    status = await asyncio.to_thread(run_rule_integrity_check)
    return ToolGuardRuleIntegrityResponse(**status)
