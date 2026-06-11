import { request } from "../request";
import type {
  CredentialBindableService,
  CredentialCreateRequest,
  CredentialGovernanceAuditEvent,
  CredentialGovernancePolicy,
  CredentialGovernancePolicyPayload,
  CredentialItem,
  CredentialMcpAutoBindResult,
  CredentialScope,
  CredentialUpdateRequest,
} from "../types";

export const credentialsApi = {
  listCredentials: (scope: CredentialScope = "visible", agentId?: string) => {
    const params = new URLSearchParams({ scope });
    if (agentId) params.set("agent_id", agentId);
    return request<CredentialItem[]>(`/credentials?${params.toString()}`);
  },

  getCredential: (
    credentialId: string,
    scope: CredentialScope = "visible",
    agentId?: string,
  ) => {
    const params = new URLSearchParams({ scope });
    if (agentId) params.set("agent_id", agentId);
    return request<CredentialItem>(
      `/credentials/${encodeURIComponent(credentialId)}?${params.toString()}`,
    );
  },

  createCredential: (payload: CredentialCreateRequest) =>
    request<{ id: string; scope: string; agent_id: string }>("/credentials", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateCredential: (
    credentialId: string,
    payload: CredentialUpdateRequest,
    scope: "agent" | "global" = "agent",
    agentId?: string,
  ) => {
    const params = new URLSearchParams({ scope });
    if (agentId) params.set("agent_id", agentId);
    return request<{ id: string; updated_at: number }>(
      `/credentials/${encodeURIComponent(credentialId)}?${params.toString()}`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      },
    );
  },

  deleteCredential: (
    credentialId: string,
    scope: "agent" | "global" = "agent",
    agentId?: string,
  ) => {
    const params = new URLSearchParams({ scope });
    if (agentId) params.set("agent_id", agentId);
    return request<{ id: string; deleted: boolean }>(
      `/credentials/${encodeURIComponent(credentialId)}?${params.toString()}`,
      {
        method: "DELETE",
      },
    );
  },

  migrateProviderCredentials: () =>
    request<{ migrated_providers: string[]; count: number }>(
      "/credentials/migrate/providers",
      {
        method: "POST",
      },
    ),

  migrateMcpCredentials: (agentId?: string) => {
    const params = new URLSearchParams();
    if (agentId) params.set("agent_id", agentId);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request<{ migrated_clients: string[]; count: number }>(
      `/credentials/migrate/mcp${suffix}`,
      { method: "POST" },
    );
  },

  listCredentialBindableServices: (agentId: string) => {
    const params = new URLSearchParams({ agent_id: agentId });
    return request<CredentialBindableService[]>(
      `/credential-bindings/services?${params.toString()}`,
    );
  },

  listCredentialGovernanceAudit: (params: {
    agentId?: string;
    serviceId?: string;
    credentialId?: string;
    decision?: string;
    limit?: number;
  }) => {
    const search = new URLSearchParams();
    if (params.agentId) search.set("agent_id", params.agentId);
    if (params.serviceId) search.set("service_id", params.serviceId);
    if (params.credentialId) search.set("credential_id", params.credentialId);
    if (params.decision) search.set("decision", params.decision);
    if (params.limit) search.set("limit", String(params.limit));
    return request<CredentialGovernanceAuditEvent[]>(
      `/credential-bindings/audit?${search.toString()}`,
    );
  },

  autoBindMcpCredentials: (agentId: string) => {
    const params = new URLSearchParams({ agent_id: agentId });
    return request<CredentialMcpAutoBindResult>(
      `/credential-bindings/mcp/auto-bind?${params.toString()}`,
      { method: "POST" },
    );
  },

  listCredentialGovernancePolicies: () =>
    request<CredentialGovernancePolicy[]>("/credential-bindings/policies"),

  createCredentialGovernancePolicy: (
    payload: CredentialGovernancePolicyPayload,
  ) =>
    request<CredentialGovernancePolicy>("/credential-bindings/policies", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateCredentialGovernancePolicy: (
    policyId: string,
    payload: Partial<CredentialGovernancePolicyPayload>,
  ) =>
    request<CredentialGovernancePolicy>(
      `/credential-bindings/policies/${encodeURIComponent(policyId)}`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      },
    ),

  deleteCredentialGovernancePolicy: (policyId: string) =>
    request<{ id: string; deleted: boolean }>(
      `/credential-bindings/policies/${encodeURIComponent(policyId)}`,
      { method: "DELETE" },
    ),
};

