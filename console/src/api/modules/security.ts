import { request } from "../request";
import { getApiUrl } from "../config";

export interface ToolGuardRule {
  id: string;
  tools: string[];
  params: string[];
  category: string;
  severity: string;
  patterns: string[];
  exclude_patterns: string[];
  description: string;
  remediation: string;
}

export interface ToolGuardConfig {
  enabled: boolean;
  guarded_tools: string[] | null;
  denied_tools: string[];
  custom_rules: ToolGuardRule[];
  disabled_rules: string[];
  auto_denied_rules: string[];
  shell_evasion_checks: Record<string, boolean>;
}

export interface ToolGuardRuleIntegrityFinding {
  file: string;
  reason: string;
  expected_sha256?: string | null;
  actual_sha256?: string | null;
  detail: string;
}

export interface ToolGuardRulesIntegrity {
  ok: boolean;
  status: string;
  message: string;
  checked_at?: string | null;
  findings: ToolGuardRuleIntegrityFinding[];
}

export interface ToolGuardRulesIntegrityRepair {
  ok: boolean;
  message: string;
  source_url: string;
  backup_path?: string | null;
  integrity: ToolGuardRulesIntegrity;
}

// ── Integrity Protection types ─────────────────────────────────────

export interface IntegrityProtectionSettings {
  persona_protection_enabled: boolean;
  source_trust_verification_enabled: boolean;
  health_check_enabled: boolean;
  rule_integrity_check_passive: boolean;
  protected_paths: string[];
  menus: string[];
}

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

export interface SourceTrustVerifyResponse {
  status: string;
  trusted: boolean;
  reason: string;
  publisher?: string | null;
  package_sha256?: string | null;
  installed: boolean;
  executed: boolean;
  verification_scheme: string;
}

export interface HealthCheckItem {
  [key: string]: unknown;
  group: string;
  id: string;
  label?: string;
  status: string;
  detail: string;
  risk: string;
  recommendation: string;
  fix_id?: string | null;
  deep_only: boolean;
}

export interface HealthCheckRepairSuggestion {
  label: string;
  doctor_fix_id: string;
  requires_confirmation: boolean;
}

export interface HealthCheckScanResponse {
  scan_id: string;
  read_only: boolean;
  progress: number;
  check_items: HealthCheckItem[];
  risk_summary: string[];
  repair_suggestions: HealthCheckRepairSuggestion[];
  mutated_files: string[];
}

export interface HealthCheckFixResponse {
  confirmed: boolean;
  selected_repair: string;
  fix_id: string;
  executed: boolean;
  exit_code: number;
  output: string[];
}

// ── File Guard types ──────────────────────────────────────────────

export interface FileGuardResponse {
  enabled: boolean;
  paths: string[];
}

export interface FileGuardUpdateBody {
  enabled?: boolean;
  paths?: string[];
}

// ── Skill Scanner types ────────────────────────────────────────────

export interface SkillScannerWhitelistEntry {
  skill_name: string;
  content_hash: string;
  added_at: string;
}

export type SkillScannerMode = "block" | "warn" | "off";

export interface SkillScannerConfig {
  mode: SkillScannerMode;
  timeout: number;
  whitelist: SkillScannerWhitelistEntry[];
}

export interface BlockedSkillFinding {
  severity: string;
  title: string;
  description: string;
  file_path: string;
  line_number: number | null;
  rule_id: string;
}

export interface BlockedSkillRecord {
  skill_name: string;
  blocked_at: string;
  max_severity: string;
  findings: BlockedSkillFinding[];
  content_hash: string;
  action: "blocked" | "warned";
}

export interface SecurityScanErrorResponse {
  type: "security_scan_failed";
  detail: string;
  skill_name: string;
  max_severity: string;
  findings: BlockedSkillFinding[];
}

// ── Allow No Auth Hosts types ──────────────────────────────────────

export interface AllowNoAuthHostsResponse {
  hosts: string[];
}

export interface AllowNoAuthHostsUpdateBody {
  hosts: string[];
}

export const securityApi = {
  // ── Tool Guard ──────────────────────────────────────────────────

  getToolGuard: () => request<ToolGuardConfig>("/config/security/tool-guard"),

  updateToolGuard: (body: ToolGuardConfig) =>
    request<ToolGuardConfig>("/config/security/tool-guard", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  getBuiltinRules: () =>
    request<ToolGuardRule[]>("/config/security/tool-guard/builtin-rules"),

  getToolGuardRulesIntegrity: () =>
    request<ToolGuardRulesIntegrity>(
      "/config/security/tool-guard/rules-integrity",
    ),

  repairToolGuardRulesIntegrity: () =>
    request<ToolGuardRulesIntegrityRepair>(
      "/config/security/tool-guard/rules-integrity/repair",
      { method: "POST" },
    ),

  // ── Integrity Protection ────────────────────────────────────────

  getIntegrityProtectionSettings: () =>
    request<IntegrityProtectionSettings>(
      "/config/security/integrity-protection/settings",
    ),

  verifyIntegritySourceTrustPackage: (packagePath: string) =>
    request<SourceTrustVerifyResponse>(
      "/config/security/integrity-protection/source-trust/verify",
      {
        method: "POST",
        body: JSON.stringify({ package_path: packagePath }),
      },
    ),

  runIntegrityHealthCheckScan: (deep: boolean = false) =>
    request<HealthCheckScanResponse>(
      "/config/security/integrity-protection/health-check/scan",
      {
        method: "POST",
        body: JSON.stringify({ deep }),
      },
    ),

  runIntegrityHealthCheckFix: (
    selectedRepair: string,
    confirmationPhrase: string,
  ) =>
    request<HealthCheckFixResponse>(
      "/config/security/integrity-protection/health-check/fix",
      {
        method: "POST",
        body: JSON.stringify({
          selected_repair: selectedRepair,
          confirmation_phrase: confirmationPhrase,
        }),
      },
    ),

  checkIntegrityRuleEntry: () =>
    request<ToolGuardRulesIntegrity>(
      "/config/security/integrity-protection/rules-integrity/check",
      { method: "POST" },
    ),

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

  // ── File Guard ─────────────────────────────────────────────────

  getFileGuard: () => request<FileGuardResponse>("/config/security/file-guard"),

  updateFileGuard: (body: FileGuardUpdateBody) =>
    request<FileGuardResponse>("/config/security/file-guard", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  // ── Skill Scanner ───────────────────────────────────────────────

  getSkillScanner: () =>
    request<SkillScannerConfig>("/config/security/skill-scanner"),

  updateSkillScanner: (body: SkillScannerConfig) =>
    request<SkillScannerConfig>("/config/security/skill-scanner", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  getBlockedHistory: () =>
    request<BlockedSkillRecord[]>(
      "/config/security/skill-scanner/blocked-history",
    ),

  clearBlockedHistory: () =>
    request<{ cleared: boolean }>(
      "/config/security/skill-scanner/blocked-history",
      { method: "DELETE" },
    ),

  removeBlockedEntry: (index: number) =>
    request<{ removed: boolean }>(
      `/config/security/skill-scanner/blocked-history/${index}`,
      { method: "DELETE" },
    ),

  addToWhitelist: (skillName: string, contentHash: string = "") =>
    request<{ whitelisted: boolean; skill_name: string }>(
      "/config/security/skill-scanner/whitelist",
      {
        method: "POST",
        body: JSON.stringify({
          skill_name: skillName,
          content_hash: contentHash,
        }),
      },
    ),

  removeFromWhitelist: (skillName: string) =>
    request<{ removed: boolean; skill_name: string }>(
      `/config/security/skill-scanner/whitelist/${encodeURIComponent(
        skillName,
      )}`,
      { method: "DELETE" },
    ),

  // ── Allow No Auth Hosts ─────────────────────────────────────────

  getAllowNoAuthHosts: () =>
    request<AllowNoAuthHostsResponse>("/config/security/allow-no-auth-hosts"),

  updateAllowNoAuthHosts: (body: AllowNoAuthHostsUpdateBody) =>
    request<AllowNoAuthHostsResponse>("/config/security/allow-no-auth-hosts", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
};
