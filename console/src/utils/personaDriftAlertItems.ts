import type { InboxEvent } from "../api/modules/console";
import type { PersonaProtectionAlert } from "../api/modules/security";

export interface PersonaDriftAlertItem {
  alertId: string;
  inboxEventId?: string;
  path: string;
  title: string;
  body: string;
  provenance: string;
}

export interface PersonaDriftAlertCopy {
  title: string;
  body: string;
}

export function mapInboxEventsByAlertId(
  events: InboxEvent[],
): Map<string, InboxEvent> {
  const byAlertId = new Map<string, InboxEvent>();
  for (const event of events) {
    if ((event.event_type || "").toLowerCase() !== "persona_drift") {
      continue;
    }
    const alertId =
      event.source_id ||
      (typeof event.payload?.alert_id === "string"
        ? event.payload.alert_id
        : "");
    if (alertId) {
      byAlertId.set(alertId, event);
    }
  }
  return byAlertId;
}

export function mergeAlertItems(
  openAlerts: PersonaProtectionAlert[],
  inboxByAlertId: Map<string, InboxEvent>,
  localize: (alert: PersonaProtectionAlert) => PersonaDriftAlertCopy,
): PersonaDriftAlertItem[] {
  return openAlerts.map((alert) => {
    const inboxEvent = inboxByAlertId.get(alert.alert_id);
    const { title, body } = localize(alert);
    return {
      alertId: alert.alert_id,
      inboxEventId: inboxEvent?.id,
      path: alert.path,
      title,
      body,
      provenance: alert.provenance,
    };
  });
}
