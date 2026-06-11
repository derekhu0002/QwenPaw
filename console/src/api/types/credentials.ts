export type CredentialScope = "agent" | "global" | "visible";

export type CredentialType = "aksk" | "token" | "api_key" | "cookie" | "custom_kv";

export interface CredentialRef {
  credential_id: string;
  field_map: Record<string, string>;
}

export interface CredentialItem {
  id: string;
  name: string;
  type: CredentialType;
  scope: "agent" | "global";
  agent_id: string;
  description: string;
  data: Record<string, string>;
  service_id: string;
  allowed_hosts: string[];
  field_map: Record<string, string>;
  created_at: number;
  updated_at: number;
}

export interface CredentialCreateRequest {
  name: string;
  type: CredentialType;
  scope: "agent" | "global";
  agent_id?: string;
  description?: string;
  data: Record<string, string>;
  service_id?: string;
  allowed_hosts?: string[];
  field_map?: Record<string, string>;
}

export interface CredentialUpdateRequest {
  name?: string;
  type?: CredentialType;
  description?: string;
  data?: Record<string, string>;
  service_id?: string;
  allowed_hosts?: string[];
  field_map?: Record<string, string>;
}

export interface CredentialBindableService {
  service_id: string;
  type: "mcp" | "tool" | "channel" | "plugin";
  name: string;
  display_name: string;
  allowed_hosts: string[];
  supported_fields: string[];
  enabled: boolean;
}

export interface CredentialGovernanceAuditEvent {
  timestamp: number;
  agent_id: string;
  request_type: string;
  service_id: string;
  credential_id: string;
  target_host: string;
  decision: "allow" | "deny" | "fallback" | string;
  decision_source: string;
  policy_id: string;
  reason_code: string;
  mapped_keys: string[];
}

export interface CredentialMcpAutoBindResult {
  updated: Array<{
    client: string;
    credential_id: string;
    service_id: string;
    allowed_hosts: string[];
    field_map: Record<string, string>;
  }>;
  skipped: Array<{
    client: string;
    reason: string;
  }>;
  count: number;
}

export interface CredentialGovernancePolicy {
  id: string;
  name: string;
  enabled: boolean;
  effect: "permit" | "deny";
  agent_id: string;
  service_id: string;
  credential_id: string;
  allowed_hosts: string[];
  allowed_mapped_keys: string[];
  cedar_text: string;
  created_at: number;
  updated_at: number;
}

export interface CredentialGovernancePolicyPayload {
  name: string;
  enabled?: boolean;
  effect?: "permit" | "deny";
  agent_id?: string;
  service_id?: string;
  credential_id?: string;
  allowed_hosts?: string[];
  allowed_mapped_keys?: string[];
  cedar_text?: string;
}

