import { useCallback, useEffect, useState } from "react";
import { Button, Card, Input, Switch, Table, Tag } from "@agentscope-ai/design";
import { Modal, Space, message } from "antd";
import { useTranslation } from "react-i18next";
import api from "../../../../api";
import { usePersonaDriftWatch } from "../../../../hooks/usePersonaDriftWatch";
import {
  acceptPersonaAlert,
  restorePersonaAlert,
} from "../../../../utils/personaAlertActions";
import type {
  IntegrityProtectionSettings,
  PersonaProtectionAlert,
  PersonaProtectionSettings,
  SourceTrustVerifyResponse,
  ToolGuardRulesIntegrity,
} from "../../../../api/modules/security";
import styles from "../index.module.less";


interface IntegrityCheckSectionProps {
  onAlertCountChange?: (count: number) => void;
  highlightAlertId?: string;
}

export function IntegrityCheckSection({
  onAlertCountChange,
  highlightAlertId,
}: IntegrityCheckSectionProps) {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<IntegrityProtectionSettings | null>(
    null,
  );
  const [personaSettings, setPersonaSettings] =
    useState<PersonaProtectionSettings | null>(null);
  const [personaAlerts, setPersonaAlerts] = useState<PersonaProtectionAlert[]>(
    [],
  );
  const [packagePath, setPackagePath] = useState("");
  const [sourceTrustResult, setSourceTrustResult] =
    useState<SourceTrustVerifyResponse | null>(null);
  const [ruleIntegrity, setRuleIntegrity] =
    useState<ToolGuardRulesIntegrity | null>(null);
  const [loading, setLoading] = useState(false);
  const [personaSwitchLoading, setPersonaSwitchLoading] = useState(false);
  const [restoringAlertId, setRestoringAlertId] = useState<string | null>(null);
  const [acceptingAlertId, setAcceptingAlertId] = useState<string | null>(null);

  const loadPersonaData = useCallback(async () => {
    const [persona, alerts] = await Promise.all([
      api.getPersonaProtectionSettings(),
      api.getPersonaProtectionAlerts(),
    ]);
    setPersonaSettings(persona);
    setPersonaAlerts(alerts.alerts);
    onAlertCountChange?.(alerts.open_alert_count);
  }, [onAlertCountChange]);

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
  }, [loadPersonaData]);

  usePersonaDriftWatch(
    (event) => {
      if (
        event.type === "persona_drift" ||
        event.type === "persona_alert_resolved" ||
        event.type === "persona_baseline_updated"
      ) {
        void loadPersonaData();
      }
    },
    Boolean(personaSettings?.enabled),
  );

  useEffect(() => {
    if (!highlightAlertId || personaAlerts.length === 0) {
      return;
    }
    const matched = personaAlerts.some(
      (alert) => alert.alert_id === highlightAlertId,
    );
    if (!matched) {
      return;
    }
    const row = document.getElementById(`persona-alert-${highlightAlertId}`);
    row?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlightAlertId, personaAlerts]);

  const verifySourceTrust = async () => {
    if (!packagePath.trim()) return;
    setLoading(true);
    try {
      setSourceTrustResult(
        await api.verifyIntegritySourceTrustPackage(packagePath.trim()),
      );
    } finally {
      setLoading(false);
    }
  };

  const checkRuleIntegrity = async () => {
    setLoading(true);
    try {
      setRuleIntegrity(await api.checkIntegrityRuleEntry());
    } finally {
      setLoading(false);
    }
  };

  const applyPersonaToggle = async (
    checked: boolean,
    confirmationPhrase?: string,
  ) => {
    setPersonaSwitchLoading(true);
    try {
      const updated = await api.updatePersonaProtectionSettings({
        enabled: checked,
        confirmation_phrase: confirmationPhrase,
      });
      setPersonaSettings(updated);
      const aggregate = await api.getIntegrityProtectionSettings();
      setSettings(aggregate);
      await loadPersonaData();
      message.success(
        checked
          ? t("security.integrityProtection.personaEnableSuccess")
          : t("security.integrityProtection.personaDisableSuccess"),
      );
    } catch {
      message.error(t("security.integrityProtection.loadFailed"));
      throw new Error("persona toggle failed");
    } finally {
      setPersonaSwitchLoading(false);
    }
  };

  const onPersonaSwitchChange = async (checked: boolean) => {
    if (checked) {
      if (personaSettings?.baseline_cleared_at) {
        Modal.confirm({
          title: t("security.integrityProtection.personaReestablishTitle"),
          content: t("security.integrityProtection.personaReestablishBody"),
          okText: t("common.confirm"),
          cancelText: t("common.cancel"),
          onOk: async () => {
            await applyPersonaToggle(
              true,
              t(
                "security.integrityProtection.confirmReestablishBaselinePhrase",
              ),
            );
          },
        });
        return;
      }
    } else if ((personaSettings?.open_alert_count ?? 0) > 0) {
      Modal.confirm({
        title: t("security.integrityProtection.personaDisableWarningTitle"),
        content: t("security.integrityProtection.disableWithOpenDriftsWarning"),
        okText: t("common.confirm"),
        cancelText: t("common.cancel"),
        onOk: async () => {
          await applyPersonaToggle(false);
        },
      });
      return;
    }

    await applyPersonaToggle(checked);
  };

  const restoreAlert = async (alert: PersonaProtectionAlert) => {
    setRestoringAlertId(alert.alert_id);
    try {
      const ok = await restorePersonaAlert(alert.alert_id);
      if (!ok) {
        message.error(t("security.integrityProtection.loadFailed"));
        return;
      }
      message.success(t("security.integrityProtection.restoreSuccess"));
      await loadPersonaData();
    } finally {
      setRestoringAlertId(null);
    }
  };

  const acceptAlert = async (alert: PersonaProtectionAlert) => {
    setAcceptingAlertId(alert.alert_id);
    try {
      const ok = await acceptPersonaAlert(alert.alert_id);
      if (!ok) {
        message.error(t("security.integrityProtection.loadFailed"));
        return;
      }
      message.success(t("security.integrityProtection.acceptSuccess"));
      await loadPersonaData();
    } finally {
      setAcceptingAlertId(null);
    }
  };

  const findings = ruleIntegrity?.findings ?? [];
  const protectedPaths =
    personaSettings?.protected_targets ?? settings?.protected_paths ?? [];

  return (
    <div className={styles.sectionFileGuardContainer}>
      <Card className={styles.formCard}>
        <div className={styles.integrityGrid}>
          <div className={styles.integrityConfigItem}>
            <span className={styles.skillScannerLabel}>
              {t("security.integrityProtection.personaProtection")}
            </span>
            <Switch
              checked={personaSettings?.enabled ?? false}
              loading={personaSwitchLoading}
              onChange={(checked) => {
                void onPersonaSwitchChange(checked);
              }}
            />
          </div>
          <div className={styles.integrityConfigItem}>
            <span className={styles.skillScannerLabel}>
              {t("security.integrityProtection.sourceTrustVerification")}
            </span>
            <Switch
              checked={settings?.source_trust_verification_enabled ?? false}
              disabled
            />
          </div>
        </div>
        {protectedPaths.length > 0 && (
          <div className={styles.integrityResult}>
            <span>{t("security.integrityProtection.protectedPathsLabel")}</span>
            <Space wrap>
              {protectedPaths.map((path) => (
                <Tag key={path}>{path}</Tag>
              ))}
            </Space>
          </div>
        )}
        <p className={styles.tabDescription}>
          {t("security.integrityProtection.defaultOffNotice")}
        </p>
        <Space.Compact style={{ width: "100%" }}>
          <Input
            value={packagePath}
            onChange={(event) => setPackagePath(event.target.value)}
            placeholder={t(
              "security.integrityProtection.packagePathPlaceholder",
            )}
            allowClear
          />
          <Button type="primary" loading={loading} onClick={verifySourceTrust}>
            {t("security.integrityProtection.verifySourceTrust")}
          </Button>
        </Space.Compact>
        {sourceTrustResult && (
          <div className={styles.integrityResult}>
            <Tag color={sourceTrustResult.trusted ? "green" : "red"}>
              {sourceTrustResult.status}
            </Tag>
            <span>{sourceTrustResult.reason}</span>
          </div>
        )}
      </Card>

      {personaSettings?.enabled && personaAlerts.length > 0 && (
        <div className={styles.personaAlertBanner}>
          {t("security.integrityProtection.personaAlertsTitle")}:{" "}
          {personaAlerts.length}
        </div>
      )}

      {personaSettings?.enabled && (
        <Card className={styles.tableCard}>
          <div className={styles.sectionHeader}>
            <h3 className={styles.sectionTitle}>
              {t("security.integrityProtection.personaAlertsTitle")}
            </h3>
          </div>
          <Table
            rowKey="alert_id"
            dataSource={personaAlerts}
            pagination={false}
            size="small"
            rowClassName={(record) =>
              record.alert_id === highlightAlertId
                ? styles.personaAlertHighlightRow
                : ""
            }
            onRow={(record) => ({
              id: `persona-alert-${record.alert_id}`,
            })}
            locale={{
              emptyText: t("security.integrityProtection.personaAlertsEmpty"),
            }}
            columns={[
              {
                title: t("security.integrityProtection.columns.file"),
                dataIndex: "path",
                key: "path",
              },
              {
                title: t("security.integrityProtection.columns.reason"),
                dataIndex: "provenance",
                key: "provenance",
              },
              {
                title: t("security.integrityProtection.columns.detail"),
                key: "detail",
                render: (_, record) =>
                  `${record.approved_sha256.slice(0, 8)} → ${record.current_sha256.slice(0, 8)}`,
              },
              {
                title: t("security.integrityProtection.columns.actions"),
                key: "actions",
                render: (_, record) => (
                  <Space>
                    <Button
                      size="small"
                      loading={restoringAlertId === record.alert_id}
                      onClick={() => {
                        void restoreAlert(record);
                      }}
                    >
                      {t("security.integrityProtection.restoreAction")}
                    </Button>
                    <Button
                      size="small"
                      type="primary"
                      loading={acceptingAlertId === record.alert_id}
                      onClick={() => {
                        void acceptAlert(record);
                      }}
                    >
                      {t("security.integrityProtection.acceptAction")}
                    </Button>
                  </Space>
                ),
              },
            ]}
          />
        </Card>
      )}

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
