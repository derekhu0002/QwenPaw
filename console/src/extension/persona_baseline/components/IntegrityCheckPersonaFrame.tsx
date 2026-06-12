import { useEffect, useState, type ReactNode } from "react";
import api from "@/api";
import type { IntegrityProtectionSettings } from "@/api/modules/security";
import {
  PersonaProtectionProvider,
  usePersonaProtectionContext,
} from "./PersonaProtectionSection";

export interface IntegrityCheckPersonaFrameProps {
  highlightAlertId?: string;
  onAlertCountChange?: (count: number) => void;
  children: (ctx: {
    settings: IntegrityProtectionSettings | null;
    setSettings: (settings: IntegrityProtectionSettings) => void;
  }) => ReactNode;
}

function IntegrityCheckPersonaLoader({
  settings,
  setSettings,
  children,
}: {
  settings: IntegrityProtectionSettings | null;
  setSettings: (settings: IntegrityProtectionSettings) => void;
  children: (ctx: {
    settings: IntegrityProtectionSettings | null;
    setSettings: (settings: IntegrityProtectionSettings) => void;
  }) => ReactNode;
}) {
  const { loadPersonaData } = usePersonaProtectionContext();

  useEffect(() => {
    Promise.all([
      api.getIntegrityProtectionSettings().then(setSettings),
      loadPersonaData(),
    ]).catch(() => {
      setSettings({
        persona_protection_enabled: false,
        source_trust_verification_enabled: false,
        health_check_enabled: false,
        rule_integrity_check_passive: true,
        protected_paths: [],
        menus: ["Tool Guard", "File Guard", "Integrity Check", "Health Check"],
      });
    });
  }, [loadPersonaData, setSettings]);

  return <>{children({ settings, setSettings })}</>;
}

export function IntegrityCheckPersonaFrame({
  highlightAlertId,
  onAlertCountChange,
  children,
}: IntegrityCheckPersonaFrameProps) {
  const [settings, setSettings] = useState<IntegrityProtectionSettings | null>(
    null,
  );

  return (
    <PersonaProtectionProvider
      highlightAlertId={highlightAlertId}
      onAlertCountChange={onAlertCountChange}
      onIntegritySettingsSync={setSettings}
    >
      <IntegrityCheckPersonaLoader settings={settings} setSettings={setSettings}>
        {children}
      </IntegrityCheckPersonaLoader>
    </PersonaProtectionProvider>
  );
}
