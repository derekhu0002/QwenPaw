import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Button, Card, Switch, Table, Tag } from "@agentscope-ai/design";
import { Modal, Space, message } from "antd";
import { useTranslation } from "react-i18next";
import api from "@/api";
import type { IntegrityProtectionSettings } from "@/api/modules/security";
import { usePersonaDriftWatch } from "../hooks/usePersonaDriftWatch";
import {
  acceptPersonaAlert,
  restorePersonaAlert,
} from "../lib/alertActions";
import type {
  PersonaProtectionAlert,
  PersonaProtectionSettings,
} from "../api/client";
import styles from "@/pages/Settings/Security/index.module.less";

interface PersonaProtectionContextValue {
  personaSettings: PersonaProtectionSettings | null;
  personaAlerts: PersonaProtectionAlert[];
  personaSwitchLoading: boolean;
  restoringAlertId: string | null;
  acceptingAlertId: string | null;
  protectedPaths: string[];
  loadPersonaData: () => Promise<void>;
  onPersonaSwitchChange: (checked: boolean) => Promise<void>;
  restoreAlert: (alert: PersonaProtectionAlert) => Promise<void>;
  acceptAlert: (alert: PersonaProtectionAlert) => Promise<void>;
}

const PersonaProtectionContext =
  createContext<PersonaProtectionContextValue | null>(null);

function usePersonaProtectionContext(): PersonaProtectionContextValue {
  const value = useContext(PersonaProtectionContext);
  if (!value) {
    throw new Error("PersonaProtection components must be used within Provider");
  }
  return value;
}

export interface PersonaProtectionProviderProps {
  children: ReactNode;
  highlightAlertId?: string;
  onAlertCountChange?: (count: number) => void;
  onIntegritySettingsSync?: (settings: IntegrityProtectionSettings) => void;
}

export function PersonaProtectionProvider({
  children,
  highlightAlertId,
  onAlertCountChange,
  onIntegritySettingsSync,
}: PersonaProtectionProviderProps) {
  const { t } = useTranslation();
  const [personaSettings, setPersonaSettings] =
    useState<PersonaProtectionSettings | null>(null);
  const [personaAlerts, setPersonaAlerts] = useState<PersonaProtectionAlert[]>(
    [],
  );
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

  const applyPersonaToggle = useCallback(
    async (checked: boolean, confirmationPhrase?: string) => {
      setPersonaSwitchLoading(true);
      try {
        const updated = await api.updatePersonaProtectionSettings({
          enabled: checked,
          confirmation_phrase: confirmationPhrase,
        });
        setPersonaSettings(updated);
        const aggregate = await api.getIntegrityProtectionSettings();
        onIntegritySettingsSync?.(aggregate);
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
    },
    [loadPersonaData, onIntegritySettingsSync, t],
  );

  const onPersonaSwitchChange = useCallback(
    async (checked: boolean) => {
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
    },
    [applyPersonaToggle, personaSettings, t],
  );

  const restoreAlert = useCallback(
    async (alert: PersonaProtectionAlert) => {
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
    },
    [loadPersonaData, t],
  );

  const acceptAlert = useCallback(
    async (alert: PersonaProtectionAlert) => {
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
    },
    [loadPersonaData, t],
  );

  const protectedPaths = personaSettings?.protected_targets ?? [];

  const value = useMemo(
    () => ({
      personaSettings,
      personaAlerts,
      personaSwitchLoading,
      restoringAlertId,
      acceptingAlertId,
      protectedPaths,
      loadPersonaData,
      onPersonaSwitchChange,
      restoreAlert,
      acceptAlert,
    }),
    [
      acceptAlert,
      acceptingAlertId,
      loadPersonaData,
      onPersonaSwitchChange,
      personaAlerts,
      personaSettings,
      personaSwitchLoading,
      protectedPaths,
      restoreAlert,
      restoringAlertId,
    ],
  );

  return (
    <PersonaProtectionContext.Provider value={value}>
      {children}
    </PersonaProtectionContext.Provider>
  );
}

export function PersonaProtectionSwitchRow() {
  const { t } = useTranslation();
  const { personaSettings, personaSwitchLoading, onPersonaSwitchChange } =
    usePersonaProtectionContext();

  return (
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
  );
}

export function PersonaProtectionProtectedPaths({
  fallbackPaths = [],
}: {
  fallbackPaths?: string[];
}) {
  const { t } = useTranslation();
  const { protectedPaths } = usePersonaProtectionContext();
  const paths =
    protectedPaths.length > 0 ? protectedPaths : fallbackPaths;

  if (paths.length === 0) {
    return null;
  }

  return (
    <div className={styles.integrityResult}>
      <span>{t("security.integrityProtection.protectedPathsLabel")}</span>
      <Space wrap>
        {paths.map((path) => (
          <Tag key={path}>{path}</Tag>
        ))}
      </Space>
    </div>
  );
}

export function PersonaProtectionAlertsCard({
  highlightAlertId,
}: {
  highlightAlertId?: string;
}) {
  const { t } = useTranslation();
  const {
    personaSettings,
    personaAlerts,
    restoringAlertId,
    acceptingAlertId,
    restoreAlert,
    acceptAlert,
  } = usePersonaProtectionContext();

  if (!personaSettings?.enabled) {
    return null;
  }

  return (
    <>
      {personaAlerts.length > 0 && (
        <div className={styles.personaAlertBanner}>
          {t("security.integrityProtection.personaAlertsTitle")}:{" "}
          {personaAlerts.length}
        </div>
      )}
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
    </>
  );
}

export { usePersonaProtectionContext };
