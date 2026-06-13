import { request } from "@/api/request";

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

export const ruleIntegrityApi = {
  getToolGuardRulesIntegrity: () =>
    request<ToolGuardRulesIntegrity>(
      "/config/security/tool-guard/rules-integrity",
    ),

  repairToolGuardRulesIntegrity: () =>
    request<ToolGuardRulesIntegrityRepair>(
      "/config/security/tool-guard/rules-integrity/repair",
      { method: "POST" },
    ),

  checkIntegrityRuleEntry: () =>
    request<ToolGuardRulesIntegrity>(
      "/config/security/integrity-protection/rules-integrity/check",
      { method: "POST" },
    ),
};
