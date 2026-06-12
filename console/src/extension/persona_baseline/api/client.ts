import { request } from "@/api/request";
import { getApiUrl } from "@/api/config";

export interface PersonaProtectionSettings {
  enabled: boolean;
  pilot_mode: boolean;
  protected_targets: string[];
  protected_paths: string[];
  baseline_established: boolean;
  baseline_cleared_at?: string | null;
  open_alert_count: number;
  scan_status?: string | null;
  last_scan_at?: string | null;
  last_scan_drift_count?: number | null;
}

export interface PersonaProtectionAlert {
  alert_id: string;
  agent_id: string;
  path: string;
  approved_sha256: string;
  current_sha256: string;
  provenance: string;
  status: string;
  detected_at: string;
  patch_path?: string | null;
}

export interface PersonaProtectionAlertsResponse {
  enabled: boolean;
  scanning: boolean;
  alerts: PersonaProtectionAlert[];
  open_alert_count: number;
}

export interface PersonaProtectionActionResponse {
  confirmed: boolean;
  message?: string;
  alert_id?: string;
  action?: string;
}

export interface PersonaProtectionSettingsUpdateBody {
  enabled?: boolean;
  protected_targets?: string[];
  confirmation_phrase?: string;
}

export const personaApi = {
  getPersonaProtectionSettings: () =>
    request<PersonaProtectionSettings>(
      "/config/security/persona-protection/settings",
    ),

  updatePersonaProtectionSettings: (body: PersonaProtectionSettingsUpdateBody) =>
    request<PersonaProtectionSettings>(
      "/config/security/persona-protection/settings",
      {
        method: "PUT",
        body: JSON.stringify(body),
      },
    ),

  getPersonaProtectionAlerts: () =>
    request<PersonaProtectionAlertsResponse>(
      "/config/security/persona-protection/alerts",
    ),

  restorePersonaProtectionAlert: (alertId: string, confirmationPhrase: string) =>
    request<PersonaProtectionActionResponse>(
      "/config/security/persona-protection/restore",
      {
        method: "POST",
        body: JSON.stringify({
          alert_id: alertId,
          confirmation_phrase: confirmationPhrase,
        }),
      },
    ),

  acceptPersonaProtectionAlert: (alertId: string, confirmationPhrase: string) =>
    request<PersonaProtectionActionResponse>(
      "/config/security/persona-protection/accept",
      {
        method: "POST",
        body: JSON.stringify({
          alert_id: alertId,
          confirmation_phrase: confirmationPhrase,
        }),
      },
    ),

  getPersonaProtectionWatchUrl: () =>
    getApiUrl("/config/security/persona-protection/watch"),
};
