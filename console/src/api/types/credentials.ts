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
}

export interface CredentialUpdateRequest {
  name?: string;
  type?: CredentialType;
  description?: string;
  data?: Record<string, string>;
}

