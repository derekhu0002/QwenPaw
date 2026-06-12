import { useState } from "react";
import { Button, Card, Table, Tag } from "@agentscope-ai/design";
import { useTranslation } from "react-i18next";
import api from "../../../../api";
import type {
  IntegrityProtectionSettings,
  ToolGuardRulesIntegrity,
} from "../../../../api/modules/security";
import {
  PersonaProtectionAlertsCard,
  PersonaProtectionProtectedPaths,
  PersonaProtectionSwitchRow,
} from "@extension/persona_baseline";
import { IntegrityCheckPersonaFrame } from "@extension/persona_baseline/components/IntegrityCheckPersonaFrame";
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
  const [ruleIntegrity, setRuleIntegrity] =
    useState<ToolGuardRulesIntegrity | null>(null);
  const [loading, setLoading] = useState(false);

  const checkRuleIntegrity = async () => {
    setLoading(true);
    try {
      setRuleIntegrity(await api.checkIntegrityRuleEntry());
    } finally {
      setLoading(false);
    }
  };

  const findings = ruleIntegrity?.findings ?? [];

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

      <Card className={styles.tableCard}>
        <div className={styles.sectionHeader}>
          <h3 className={styles.sectionTitle}>
            {t("security.integrityProtection.ruleIntegrityTitle")}
          </h3>
          <Button onClick={checkRuleIntegrity} loading={loading}>
            {t("security.integrityProtection.ruleIntegrityAction")}
          </Button>
        </div>
        {ruleIntegrity && (
          <div className={styles.integrityResult}>
            <Tag color={ruleIntegrity.ok ? "green" : "red"}>
              {ruleIntegrity.status}
            </Tag>
            <span>{ruleIntegrity.message}</span>
          </div>
        )}
        <Table
          rowKey={(_, index) => String(index)}
          dataSource={findings}
          pagination={false}
          size="small"
          locale={{
            emptyText: t("security.integrityProtection.emptyFindings"),
          }}
          columns={[
            {
              title: t("security.integrityProtection.columns.file"),
              dataIndex: "file",
              key: "file",
            },
            {
              title: t("security.integrityProtection.columns.reason"),
              dataIndex: "reason",
              key: "reason",
            },
            {
              title: t("security.integrityProtection.columns.detail"),
              dataIndex: "detail",
              key: "detail",
            },
          ]}
        />
      </Card>
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
