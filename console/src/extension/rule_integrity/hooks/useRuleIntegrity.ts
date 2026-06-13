import { useState, useEffect, useCallback } from "react";
import { ruleIntegrityApi } from "../api/client";
import type {
  ToolGuardRulesIntegrity,
  ToolGuardRulesIntegrityRepair,
} from "../api/client";

export function useRuleIntegrity(options?: { pollIntervalMs?: number }) {
  const pollIntervalMs = options?.pollIntervalMs ?? 5000;
  const [rulesIntegrity, setRulesIntegrity] =
    useState<ToolGuardRulesIntegrity | null>(null);
  const [repairingRulesIntegrity, setRepairingRulesIntegrity] = useState(false);

  const fetchRulesIntegrity = useCallback(async () => {
    try {
      setRulesIntegrity(await ruleIntegrityApi.getToolGuardRulesIntegrity());
    } catch (integrityErr) {
      console.warn(
        "Failed to load tool guard rule integrity status:",
        integrityErr,
      );
    }
  }, []);

  useEffect(() => {
    if (pollIntervalMs <= 0) {
      return undefined;
    }
    const timer = window.setInterval(fetchRulesIntegrity, pollIntervalMs);
    return () => window.clearInterval(timer);
  }, [fetchRulesIntegrity, pollIntervalMs]);

  const repairRulesIntegrity =
    useCallback(async (): Promise<ToolGuardRulesIntegrityRepair> => {
      setRepairingRulesIntegrity(true);
      try {
        const result = await ruleIntegrityApi.repairToolGuardRulesIntegrity();
        setRulesIntegrity(result.integrity);
        return result;
      } finally {
        setRepairingRulesIntegrity(false);
      }
    }, []);

  return {
    rulesIntegrity,
    repairingRulesIntegrity,
    fetchRulesIntegrity,
    repairRulesIntegrity,
  };
}
