# -*- coding: utf-8 -*-
"""Credential binding helper APIs."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ...config.config import CredentialRef, CredentialScope, load_agent_config
from ...security.credential_governance import build_mcp_service_catalog
from ...security.credential_governance.audit import get_credential_governance_audit
from ...security.credential_governance.policy_store import (
    get_credential_policy_store,
)
from ...security.credential_store import get_credential_store

router = APIRouter(
    prefix="/credential-bindings",
    tags=["credential-bindings"],
)


def _request_agent_id(request: Request, explicit_agent_id: str | None) -> str | None:
    if explicit_agent_id:
        return explicit_agent_id
    state_agent = getattr(request.state, "agent_id", None)
    if state_agent:
        return str(state_agent)
    header_agent = request.headers.get("X-Agent-Id")
    if header_agent:
        return header_agent
    return None


class CredentialPolicyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    enabled: bool = True
    effect: Literal["permit", "deny"] = "permit"
    agent_id: str = ""
    service_id: str = ""
    credential_id: str = ""
    allowed_hosts: list[str] = Field(default_factory=list)
    allowed_mapped_keys: list[str] = Field(default_factory=list)
    cedar_text: str = ""


class CredentialPolicyUpdateRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    effect: Literal["permit", "deny"] | None = None
    agent_id: str | None = None
    service_id: str | None = None
    credential_id: str | None = None
    allowed_hosts: list[str] | None = None
    allowed_mapped_keys: list[str] | None = None
    cedar_text: str | None = None


@router.get("/services")
async def list_credential_binding_services(
    request: Request,
    agent_id: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """List backend-derived services that can bind credentials."""

    resolved_agent_id = _request_agent_id(request, agent_id)
    if not resolved_agent_id:
        raise HTTPException(400, detail="agent_id is required")

    try:
        agent_config = load_agent_config(resolved_agent_id)
    except Exception as exc:
        raise HTTPException(404, detail=str(exc)) from exc

    services = build_mcp_service_catalog(agent_config.mcp)
    return [service.model_dump() for service in services]


@router.get("/policies")
async def list_credential_governance_policies() -> list[dict[str, Any]]:
    """List managed credential governance policies."""

    store = get_credential_policy_store()
    return [policy.model_dump() for policy in store.list_policies()]


@router.post("/policies", status_code=201)
async def create_credential_governance_policy(
    body: CredentialPolicyCreateRequest = Body(...),
) -> dict[str, Any]:
    """Create a managed credential governance policy."""

    store = get_credential_policy_store()
    policy = store.create_policy(**body.model_dump())
    return policy.model_dump()


@router.put("/policies/{policy_id}")
async def update_credential_governance_policy(
    policy_id: str,
    body: CredentialPolicyUpdateRequest = Body(...),
) -> dict[str, Any]:
    """Update a managed credential governance policy."""

    store = get_credential_policy_store()
    try:
        policy = store.update_policy(
            policy_id,
            **body.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    return policy.model_dump()


@router.delete("/policies/{policy_id}")
async def delete_credential_governance_policy(policy_id: str) -> dict[str, Any]:
    """Delete a managed credential governance policy."""

    store = get_credential_policy_store()
    deleted = store.delete_policy(policy_id)
    if not deleted:
        raise HTTPException(404, detail=f"Policy '{policy_id}' not found")
    return {"id": policy_id, "deleted": True}


@router.get("/audit")
async def list_credential_governance_audit(
    request: Request,
    agent_id: str | None = Query(default=None),
    service_id: str | None = Query(default=None),
    credential_id: str | None = Query(default=None),
    decision: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    """List recent governed credential injection audit events."""

    resolved_agent_id = _request_agent_id(request, agent_id)
    audit = get_credential_governance_audit()
    return audit.read(
        limit=limit,
        agent_id=resolved_agent_id,
        service_id=service_id,
        credential_id=credential_id,
        decision=decision,
    )


@router.post("/mcp/auto-bind")
async def auto_bind_mcp_credentials(
    request: Request,
    agent_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Bind existing agent-scoped MCP credential refs to MCP service metadata."""

    resolved_agent_id = _request_agent_id(request, agent_id)
    if not resolved_agent_id:
        raise HTTPException(400, detail="agent_id is required")

    try:
        agent_config = load_agent_config(resolved_agent_id)
    except Exception as exc:
        raise HTTPException(404, detail=str(exc)) from exc

    services = {
        service.service_id: service
        for service in build_mcp_service_catalog(agent_config.mcp)
    }
    store = get_credential_store()
    updated: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    if agent_config.mcp is None:
        return {"updated": updated, "skipped": skipped, "count": 0}

    for client_key, client in agent_config.mcp.clients.items():
        service_id = f"mcp:{client_key}"
        service = services.get(service_id)
        if service is None:
            skipped.append({"client": client_key, "reason": "service_not_found"})
            continue

        if client.credential_ref is None:
            candidates = [
                entry
                for entry in store.list_credentials(
                    scope=CredentialScope.AGENT,
                    agent_id=resolved_agent_id,
                    include_secret_data=True,
                )
                if getattr(entry, "service_id", "") == service_id
            ]
            if not candidates:
                skipped.append({"client": client_key, "reason": "no_credential_ref"})
                continue
            selected = candidates[0]
            client.credential_ref = CredentialRef(
                credential_id=selected.id,
                field_map=selected.field_map,
            )

        entry = store.get_visible_credential(
            client.credential_ref.credential_id,
            agent_id=resolved_agent_id,
        )
        if entry is None:
            skipped.append({"client": client_key, "reason": "credential_not_found"})
            continue
        if entry.scope != CredentialScope.AGENT:
            skipped.append({"client": client_key, "reason": "global_credential_skipped"})
            continue

        field_map = entry.field_map or client.credential_ref.field_map
        if not field_map:
            skipped.append({"client": client_key, "reason": "empty_field_map"})
            continue

        store.update_credential(
            entry.id,
            scope=CredentialScope.AGENT,
            agent_id=resolved_agent_id,
            service_id=service_id,
            allowed_hosts=service.allowed_hosts,
            field_map=field_map,
        )
        updated.append(
            {
                "client": client_key,
                "credential_id": entry.id,
                "service_id": service_id,
                "allowed_hosts": service.allowed_hosts,
                "field_map": field_map,
            },
        )

    return {"updated": updated, "skipped": skipped, "count": len(updated)}
