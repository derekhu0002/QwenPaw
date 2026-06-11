# -*- coding: utf-8 -*-
"""Service catalog for credential binding.

The catalog gives the UI stable, backend-derived targets such as
``mcp:github``. Users choose from these entries instead of typing internal
service identifiers by hand.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from ...config.config import MCPConfig


class SelectableService(BaseModel):
    """A service that can receive a governed credential injection."""

    service_id: str = Field(..., min_length=1)
    type: Literal["mcp", "tool", "channel", "plugin"]
    name: str
    display_name: str
    allowed_hosts: list[str] = Field(default_factory=list)
    supported_fields: list[str] = Field(default_factory=list)
    enabled: bool = True


def _host_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.hostname or ""


def build_mcp_service_catalog(mcp: MCPConfig | None) -> list[SelectableService]:
    """Build selectable MCP service entries from an agent's MCP config."""

    if mcp is None:
        return []

    services: list[SelectableService] = []
    for client_key, client in mcp.clients.items():
        allowed_hosts: list[str] = []
        if client.transport != "stdio":
            host = _host_from_url(client.url)
            if host:
                allowed_hosts.append(host)

        services.append(
            SelectableService(
                service_id=f"mcp:{client_key}",
                type="mcp",
                name=client_key,
                display_name=f"MCP: {client_key}",
                allowed_hosts=allowed_hosts,
                supported_fields=[
                    "header.*",
                    "header.Authorization",
                    "env.*",
                ],
                enabled=client.enabled,
            ),
        )
    return services
