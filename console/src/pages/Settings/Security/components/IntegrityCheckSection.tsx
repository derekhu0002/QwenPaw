import {
  PersonaProtectionAlertsCard,
  PersonaProtectionProtectedPaths,
  PersonaProtectionSwitchRow,
} from "@extension/persona_baseline";
import { IntegrityCheckPersonaFrame } from "@extension/persona_baseline/components/IntegrityCheckPersonaFrame";
import { RuleIntegrityPassiveCard } from "@extension/rule_integrity";
import type { IntegrityProtectionSettings } from "../../../../api/modules/security";
import { Card } from "@agentscope-ai/design";
import { useTranslation } from "react-i18next";
import styles from "../index.module.less";

interface IntegrityCheckSectionProps {
  onAlertCountChange?: (count: number) => void;
  highlightAlertId?: string;
}

function IntegrityCheckDeliverySection({
  highlightAlertId,
  settings,
}: {
  highlightAlertId?: string;
  settings: IntegrityProtectionSettings | null;
}) {
  const { t } = useTranslation();

  return (
    <div className={styles.sectionFileGuardContainer}>
      <Card className={styles.formCard}>
        <div className={styles.integrityGrid}>
          <PersonaProtectionSwitchRow />
        </div>
        <PersonaProtectionProtectedPaths
          fallbackPaths={settings?.protected_paths ?? []}
        />
        <p className={styles.tabDescription}>
          {t("security.integrityProtection.defaultOffNotice")}
        </p>
      </Card>

      <PersonaProtectionAlertsCard highlightAlertId={highlightAlertId} />

      <RuleIntegrityPassiveCard />
    </div>
  );
}

export function IntegrityCheckSection({
  onAlertCountChange,
  highlightAlertId,
}: IntegrityCheckSectionProps) {
  return (
    <IntegrityCheckPersonaFrame
      highlightAlertId={highlightAlertId}
      onAlertCountChange={onAlertCountChange}
    >
      {({ settings }) => (
        <IntegrityCheckDeliverySection
          highlightAlertId={highlightAlertId}
          settings={settings}
        />
      )}
    </IntegrityCheckPersonaFrame>
  );
}
