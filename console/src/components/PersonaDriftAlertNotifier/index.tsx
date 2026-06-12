import { useCallback, useEffect, useState } from "react";
import { Button } from "@agentscope-ai/design";
import { message } from "antd";
import { ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import api from "../../api";
import { usePersonaDriftWatch } from "../../hooks/usePersonaDriftWatch";
import {
  acceptPersonaAlert,
  restorePersonaAlert,
} from "../../utils/personaAlertActions";
import {
  getPersonaDriftBody,
  getPersonaDriftTitle,
} from "../../utils/personaDriftDisplay";
import {
  mapInboxEventsByAlertId,
  mergeAlertItems,
  type PersonaDriftAlertItem,
} from "../../utils/personaDriftAlertItems";
import styles from "./index.module.less";

const PERSONA_SETTINGS_POLL_MS = 15_000;
const ALERTS_SYNC_POLL_MS = 8_000;
const MAX_VISIBLE_ALERTS = 3;

export default function PersonaDriftAlertNotifier() {
  const { t } = useTranslation();
  const [personaEnabled, setPersonaEnabled] = useState(false);
  const [alerts, setAlerts] = useState<PersonaDriftAlertItem[]>([]);
  const [actionLoading, setActionLoading] = useState<
    Record<string, "restore" | "accept" | null>
  >({});

  const syncAlerts = useCallback(async () => {
    if (!personaEnabled) {
      setAlerts([]);
      return;
    }
    try {
      const [inboxRes, alertsRes] = await Promise.all([
        api.getInboxEvents({
          source_type: "persona_protection",
          unread_only: true,
          limit: 50,
        }),
        api.getPersonaProtectionAlerts(),
      ]);
      const inboxByAlertId = mapInboxEventsByAlertId(inboxRes?.events ?? []);
      const merged = mergeAlertItems(
        alertsRes.alerts,
        inboxByAlertId,
        (alert) => ({
          title: getPersonaDriftTitle(t, alert.provenance),
          body: getPersonaDriftBody(t, alert.path),
        }),
      );
      setAlerts(merged.slice(0, MAX_VISIBLE_ALERTS));
    } catch {
      // Keep previous alerts when sync fails.
    }
  }, [personaEnabled, t]);

  const refreshPersonaEnabled = useCallback(async () => {
    try {
      const settings = await api.getPersonaProtectionSettings();
      setPersonaEnabled(Boolean(settings.enabled));
    } catch {
      setPersonaEnabled(false);
    }
  }, []);

  useEffect(() => {
    void refreshPersonaEnabled();
    const timer = window.setInterval(() => {
      void refreshPersonaEnabled();
    }, PERSONA_SETTINGS_POLL_MS);
    return () => window.clearInterval(timer);
  }, [refreshPersonaEnabled]);

  useEffect(() => {
    void syncAlerts();
    if (!personaEnabled) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      void syncAlerts();
    }, ALERTS_SYNC_POLL_MS);
    return () => window.clearInterval(timer);
  }, [personaEnabled, syncAlerts]);

  usePersonaDriftWatch(
    (event) => {
      if (event.type === "persona_drift") {
        void syncAlerts();
        return;
      }
      if (event.type === "persona_alert_resolved") {
        setAlerts((prev) =>
          prev.filter((item) => item.alertId !== event.alert_id),
        );
        void syncAlerts();
      }
    },
    personaEnabled,
  );

  const runAction = async (
    item: PersonaDriftAlertItem,
    action: "restore" | "accept",
  ) => {
    setActionLoading((prev) => ({ ...prev, [item.alertId]: action }));
    try {
      const ok =
        action === "restore"
          ? await restorePersonaAlert(item.alertId, item.inboxEventId)
          : await acceptPersonaAlert(item.alertId, item.inboxEventId);
      if (!ok) {
        message.error(t("security.integrityProtection.loadFailed"));
        return;
      }
      message.success(
        action === "restore"
          ? t("security.integrityProtection.restoreSuccess")
          : t("security.integrityProtection.acceptSuccess"),
      );
      setAlerts((prev) =>
        prev.filter((alert) => alert.alertId !== item.alertId),
      );
      void syncAlerts();
    } finally {
      setActionLoading((prev) => ({ ...prev, [item.alertId]: null }));
    }
  };

  if (!personaEnabled || alerts.length === 0) {
    return null;
  }

  return (
    <div
      className={styles.wrap}
      role="region"
      aria-label={t("security.integrityProtection.personaDriftAlertTitle")}
    >
      {alerts.map((item) => {
        const loading = actionLoading[item.alertId];
        return (
          <article key={item.alertId} className={styles.card}>
            <div className={styles.header}>
              <ShieldAlert size={22} className={styles.icon} aria-hidden />
              <div className={styles.titleBlock}>
                <h4 className={styles.title}>{item.title}</h4>
                <p className={styles.subtitle}>{item.path}</p>
              </div>
            </div>
            <p className={styles.body}>{item.body}</p>
            <div className={styles.actions}>
              <Button
                size="small"
                loading={loading === "restore" ? true : undefined}
                disabled={Boolean(loading && loading !== "restore")}
                onClick={() => {
                  void runAction(item, "restore");
                }}
              >
                {t("security.integrityProtection.restoreAction")}
              </Button>
              <Button
                size="small"
                type="primary"
                loading={loading === "accept" ? true : undefined}
                disabled={Boolean(loading && loading !== "accept")}
                onClick={() => {
                  void runAction(item, "accept");
                }}
              >
                {t("security.integrityProtection.acceptAction")}
              </Button>
            </div>
          </article>
        );
      })}
    </div>
  );
}
