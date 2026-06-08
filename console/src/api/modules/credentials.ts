import { request } from "../request";
import type {
  CredentialCreateRequest,
  CredentialItem,
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
};

