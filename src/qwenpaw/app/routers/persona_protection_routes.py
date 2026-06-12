# -*- coding: utf-8 -*-
"""Persona baseline protection API routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ...security.extension_host import get_persona_service, stream_persona_events
from .schemas_integrity_delivery import (
    PersonaProtectionActionRequest,
    PersonaProtectionActionResponse,
    PersonaProtectionAlertsResponse,
    PersonaProtectionSettingsResponse,
    PersonaProtectionSettingsUpdateRequest,
)

router = APIRouter(tags=["config"])


@router.get(
    "/security/persona-protection/settings",
    response_model=PersonaProtectionSettingsResponse,
    summary="Get persona baseline protection settings",
)
async def get_persona_protection_settings() -> PersonaProtectionSettingsResponse:
    return PersonaProtectionSettingsResponse(
        **get_persona_service().get_settings_payload(),
    )


@router.put(
    "/security/persona-protection/settings",
    response_model=PersonaProtectionSettingsResponse,
    summary="Update persona baseline protection settings",
)
async def update_persona_protection_settings(
    body: PersonaProtectionSettingsUpdateRequest,
) -> PersonaProtectionSettingsResponse:
    service = get_persona_service()
    try:
        payload = await service.update_settings(
            enabled=body.enabled,
            protected_targets=body.protected_targets,
            confirmation_phrase=body.confirmation_phrase,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return PersonaProtectionSettingsResponse(**payload)


@router.get(
    "/security/persona-protection/alerts",
    response_model=PersonaProtectionAlertsResponse,
    summary="List open persona drift alerts",
)
async def get_persona_protection_alerts() -> PersonaProtectionAlertsResponse:
    payload = await get_persona_service().list_alerts()
    return PersonaProtectionAlertsResponse(**payload)


@router.post(
    "/security/persona-protection/restore",
    response_model=PersonaProtectionActionResponse,
    summary="Restore persona file from approved baseline (P2)",
)
async def restore_persona_protection_alert(
    body: PersonaProtectionActionRequest,
) -> PersonaProtectionActionResponse:
    service = get_persona_service()
    if not service.is_enabled():
        raise HTTPException(status_code=403, detail="persona protection disabled")
    result = await service.restore(
        alert_id=body.alert_id,
        confirmation_phrase=body.confirmation_phrase,
    )
    return PersonaProtectionActionResponse(**result)


@router.post(
    "/security/persona-protection/accept",
    response_model=PersonaProtectionActionResponse,
    summary="Accept current persona file as new baseline (P2)",
)
async def accept_persona_protection_alert(
    body: PersonaProtectionActionRequest,
) -> PersonaProtectionActionResponse:
    service = get_persona_service()
    if not service.is_enabled():
        raise HTTPException(status_code=403, detail="persona protection disabled")
    result = await service.accept(
        alert_id=body.alert_id,
        confirmation_phrase=body.confirmation_phrase,
    )
    return PersonaProtectionActionResponse(**result)


@router.get(
    "/security/persona-protection/watch",
    summary="SSE stream for persona drift and baseline updates",
)
async def watch_persona_protection(request: Request) -> StreamingResponse:
    return StreamingResponse(
        stream_persona_events(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
