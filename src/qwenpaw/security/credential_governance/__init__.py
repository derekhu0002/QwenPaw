# -*- coding: utf-8 -*-
"""Optional credential governance layer.

This package is intentionally separate from ``credential_store`` and
``credential_resolver``. The existing credential center remains responsible for
storage and basic runtime resolution; this layer only adds service binding,
authorization, and audit behavior for opted-in injection paths.
"""

from .gateway import CredentialInjectionGateway, get_credential_injection_gateway
from .policy import CredentialPolicyEngine, CredentialPolicyRequest
from .service_catalog import SelectableService, build_mcp_service_catalog

__all__ = [
    "CredentialInjectionGateway",
    "CredentialPolicyEngine",
    "CredentialPolicyRequest",
    "SelectableService",
    "build_mcp_service_catalog",
    "get_credential_injection_gateway",
]
