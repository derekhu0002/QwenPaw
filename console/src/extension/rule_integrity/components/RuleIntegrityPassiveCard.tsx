import { useState } from "react";
import { Button, Card, Table, Tag } from "@agentscope-ai/design";
import { useTranslation } from "react-i18next";
import { ruleIntegrityApi } from "../api/client";
import type { ToolGuardRulesIntegrity } from "../api/client";
import styles from "@/pages/Settings/Security/index.module.less";

export function RuleIntegrityPassiveCard() {
  const { t } = useTranslation();
  const [ruleIntegrity, setRuleIntegrity] =
    useState<ToolGuardRulesIntegrity | null>(null);
  const [loading, setLoading] = useState(false);

  const checkRuleIntegrity = async () => {
    setLoading(true);
    try {
      setRuleIntegrity(await ruleIntegrityApi.checkIntegrityRuleEntry());
    } finally {
      setLoading(false);
    }
  };

  const findings = ruleIntegrity?.findings ?? [];

  return (
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
  );
}
