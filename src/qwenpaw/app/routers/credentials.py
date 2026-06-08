# -*- coding: utf-8 -*-
"""Credential center CRUD APIs."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ...config.config import (
    CredentialRef,
    CredentialScope,
    CredentialType,
)
from ...config.config import save_agent_config
from ...providers.provider_manager import ProviderManager
from ...security.credential_store import get_credential_store

router = APIRouter(prefix="/credentials", tags=["credentials"])


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


class CredentialCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    type: CredentialType = Field(default=CredentialType.CUSTOM_KV)
    scope: CredentialScope = Field(default=CredentialScope.AGENT)
    agent_id: str | None = None
    description: str = ""
    data: dict[str, str] = Field(default_factory=dict)


class CredentialUpdateRequest(BaseModel):
    name: str | None = None
    type: CredentialType | None = None
    description: str | None = None
    data: dict[str, str] | None = None


@router.get("")
async def list_credentials(
    request: Request,
    scope: Literal["agent", "global", "visible"] = Query(default="visible"),
    agent_id: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    store = get_credential_store()
    resolved_agent_id = _request_agent_id(request, agent_id)

    if scope == "global":
        return store.list_credentials(scope=CredentialScope.GLOBAL)
    if scope == "agent":
        if not resolved_agent_id:
            raise HTTPException(400, detail="agent_id is required for agent scope")
        return store.list_credentials(
            scope=CredentialScope.AGENT,
            agent_id=resolved_agent_id,
        )
    if not resolved_agent_id:
        raise HTTPException(400, detail="agent_id is required for visible scope")
    return store.list_visible_credentials(resolved_agent_id)


@router.post("", status_code=201)
async def create_credential(
    request: Request,
    body: CredentialCreateRequest = Body(...),
) -> dict[str, Any]:
    store = get_credential_store()
    resolved_agent_id = _request_agent_id(request, body.agent_id)
    if body.scope == CredentialScope.AGENT and not resolved_agent_id:
        raise HTTPException(400, detail="agent_id is required for agent scope")

    entry = store.create_credential(
        name=body.name,
        credential_type=body.type,
        scope=body.scope,
        data=body.data,
        agent_id=resolved_agent_id,
        description=body.description,
    )
    return {
        "id": entry.id,
        "scope": entry.scope,
        "agent_id": entry.agent_id,
    }


@router.put("/{credential_id}")
async def update_credential(
    request: Request,
    credential_id: str,
    body: CredentialUpdateRequest = Body(...),
    scope: Literal["agent", "global"] = Query(default="agent"),
    agent_id: str | None = Query(default=None),
) -> dict[str, Any]:
    resolved_agent_id = _request_agent_id(request, agent_id)
    resolved_scope = CredentialScope(scope)
    if resolved_scope == CredentialScope.AGENT and not resolved_agent_id:
        raise HTTPException(400, detail="agent_id is required for agent scope")

    store = get_credential_store()
    try:
        entry = store.update_credential(
            credential_id,
            scope=resolved_scope,
            agent_id=resolved_agent_id,
            name=body.name,
            description=body.description,
            data=body.data,
            credential_type=body.type,
        )
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc)) from exc

    return {"id": entry.id, "updated_at": entry.updated_at}


@router.get("/{credential_id}")
async def get_credential(
    request: Request,
    credential_id: str,
    scope: Literal["agent", "global", "visible"] = Query(default="visible"),
    agent_id: str | None = Query(default=None),
) -> dict[str, Any]:
    resolved_agent_id = _request_agent_id(request, agent_id)
    store = get_credential_store()

    if scope == "global":
        entry = store.get_credential(
            credential_id,
            scope=CredentialScope.GLOBAL,
        )
    elif scope == "agent":
        if not resolved_agent_id:
            raise HTTPException(400, detail="agent_id is required for agent scope")
        entry = store.get_credential(
            credential_id,
            scope=CredentialScope.AGENT,
            agent_id=resolved_agent_id,
        )
    else:
        if not resolved_agent_id:
            raise HTTPException(400, detail="agent_id is required for visible scope")
        entry = store.get_visible_credential(
            credential_id,
            agent_id=resolved_agent_id,
        )

    if entry is None:
        raise HTTPException(404, detail=f"Credential '{credential_id}' not found")

    return entry.model_dump()


@router.delete("/{credential_id}")
async def delete_credential(
    request: Request,
    credential_id: str,
    scope: Literal["agent", "global"] = Query(default="agent"),
    agent_id: str | None = Query(default=None),
) -> dict[str, Any]:
    resolved_agent_id = _request_agent_id(request, agent_id)
    resolved_scope = CredentialScope(scope)
    if resolved_scope == CredentialScope.AGENT and not resolved_agent_id:
        raise HTTPException(400, detail="agent_id is required for agent scope")

    store = get_credential_store()
    deleted = store.delete_credential(
        credential_id,
        scope=resolved_scope,
        agent_id=resolved_agent_id,
    )
    if not deleted:
        raise HTTPException(404, detail=f"Credential '{credential_id}' not found")
    return {"id": credential_id, "deleted": True}


@router.post("/validate-ref")
async def validate_credential_ref(
    request: Request,
    credential_ref: CredentialRef = Body(...),
    agent_id: str | None = Query(default=None),
) -> dict[str, Any]:
    resolved_agent_id = _request_agent_id(request, agent_id)
    store = get_credential_store()
    entry = (
        store.get_visible_credential(
            credential_ref.credential_id,
            agent_id=resolved_agent_id,
        )
        if resolved_agent_id
        else store.get_credential(
            credential_ref.credential_id,
            scope=CredentialScope.GLOBAL,
        )
    )
    if entry is None:
        raise HTTPException(
            404,
            detail=f"Credential '{credential_ref.credential_id}' not found",
        )
    return {
        "ok": True,
        "credential_id": entry.id,
        "scope": entry.scope,
        "available_fields": sorted(entry.data.keys()),
    }


@router.post("/migrate/providers")
async def migrate_provider_credentials() -> dict[str, Any]:
    """Migrate plaintext provider api_key into credential references."""
    store = get_credential_store()
    manager = ProviderManager.get_instance()
    migrated: list[str] = []

    provider_ids = (
        list(manager.builtin_providers.keys())
        + list(manager.custom_providers.keys())
        + list(manager.plugin_providers.keys())
    )
    for provider_id in provider_ids:
        provider = manager.get_provider(provider_id)
        if provider is None:
            continue
        if not provider.api_key or provider.credential_ref is not None:
            continue
        created = store.create_credential(
            name=f"provider:{provider_id}",
            credential_type=CredentialType.API_KEY,
            scope=CredentialScope.GLOBAL,
            data={"api_key": provider.api_key},
            description="Migrated from provider.api_key",
        )
        manager.update_provider(
            provider_id,
            {
                "api_key": "",
                "credential_ref": CredentialRef(
                    credential_id=created.id,
                    field_map={"api_key": "api_key"},
                ),
            },
        )
        migrated.append(provider_id)

    return {"migrated_providers": migrated, "count": len(migrated)}


@router.post("/migrate/mcp")
async def migrate_mcp_credentials(
    request: Request,
    agent_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Migrate MCP headers/env to agent-scoped credential refs."""
    from ..agent_context import get_agent_for_request

    resolved_agent_id = _request_agent_id(request, agent_id)
    if not resolved_agent_id:
        raise HTTPException(400, detail="agent_id is required")

    workspace = await get_agent_for_request(request, agent_id=resolved_agent_id)
    agent_config = workspace.config
    if agent_config.mcp is None or not agent_config.mcp.clients:
        return {"migrated_clients": [], "count": 0}

    store = get_credential_store()
    migrated_clients: list[str] = []
    for client_key, client in agent_config.mcp.clients.items():
        if client.credential_ref is not None:
            continue
        payload: dict[str, str] = {}
        for key, value in (client.headers or {}).items():
            payload[f"header.{key}"] = value
        for key, value in (client.env or {}).items():
            payload[f"env.{key}"] = value
        if not payload:
            continue

        created = store.create_credential(
            name=f"mcp:{client_key}",
            credential_type=CredentialType.CUSTOM_KV,
            scope=CredentialScope.AGENT,
            agent_id=resolved_agent_id,
            data=payload,
            description="Migrated from MCP headers/env",
        )
        client.credential_ref = CredentialRef(credential_id=created.id, field_map={})
        client.headers = {}
        client.env = {}
        migrated_clients.append(client_key)

    if migrated_clients:
        save_agent_config(workspace.agent_id, agent_config)
    return {"migrated_clients": migrated_clients, "count": len(migrated_clients)}

