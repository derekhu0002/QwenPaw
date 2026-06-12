import api from "@/api";
import { dispatchInboxChanged } from "@extension/shared/inbox/inboxEvents";

export const PERSONA_CONFIRM_RESTORE = "Confirm persona restore";
export const PERSONA_CONFIRM_ACCEPT = "Confirm persona accept";

function eventMatchesAlert(
  event: {
    id: string;
    source_id?: string;
    read?: boolean;
    payload?: Record<string, unknown>;
  },
  alertId: string,
  preferredEventId?: string,
): boolean {
  if (preferredEventId && event.id === preferredEventId) {
    return true;
  }
  if (event.source_id === alertId) {
    return true;
  }
  return event.payload?.alert_id === alertId;
}

export async function collectUnreadPersonaInboxEventIds(
  alertId: string,
  preferredEventId?: string,
): Promise<string[]> {
  const ids = new Set<string>();
  if (preferredEventId) {
    ids.add(preferredEventId);
  }

  const res = await api.getInboxEvents({
    source_type: "persona_protection",
    limit: 200,
  });
  for (const event of res?.events ?? []) {
    if (event.read) {
      continue;
    }
    if (eventMatchesAlert(event, alertId, preferredEventId)) {
      ids.add(event.id);
    }
  }

  if (ids.size === 0) {
    const unreadRes = await api.getInboxEvents({
      unread_only: true,
      limit: 200,
    });
    for (const event of unreadRes?.events ?? []) {
      if (eventMatchesAlert(event, alertId, preferredEventId)) {
        ids.add(event.id);
      }
    }
  }

  return Array.from(ids);
}

export async function markPersonaInboxEventsAsRead(
  alertId: string,
  preferredEventId?: string,
): Promise<string[]> {
  const eventIds = await collectUnreadPersonaInboxEventIds(
    alertId,
    preferredEventId,
  );
  if (eventIds.length === 0) {
    return [];
  }

  const result = await api.markInboxRead({ event_ids: eventIds });
  if ((result?.updated ?? 0) > 0) {
    return eventIds;
  }

  // Retry once with a fresh unread scan in case the store changed between reads.
  const retryIds = await collectUnreadPersonaInboxEventIds(alertId);
  if (retryIds.length === 0) {
    return eventIds;
  }
  const retryResult = await api.markInboxRead({ event_ids: retryIds });
  if ((retryResult?.updated ?? 0) > 0) {
    return retryIds;
  }
  return [];
}

export async function markPersonaInboxReadByAlertId(
  alertId: string,
): Promise<string[]> {
  const marked = await markPersonaInboxEventsAsRead(alertId);
  if (marked.length > 0) {
    dispatchInboxChanged({ eventIds: marked, alertId });
  }
  return marked;
}

export async function restorePersonaAlert(
  alertId: string,
  inboxEventId?: string,
): Promise<boolean> {
  const result = await api.restorePersonaProtectionAlert(
    alertId,
    PERSONA_CONFIRM_RESTORE,
  );
  if (!result.confirmed) {
    return false;
  }
  const marked = await markPersonaInboxEventsAsRead(alertId, inboxEventId);
  dispatchInboxChanged({ eventIds: marked, alertId });
  return true;
}

export async function acceptPersonaAlert(
  alertId: string,
  inboxEventId?: string,
): Promise<boolean> {
  const result = await api.acceptPersonaProtectionAlert(
    alertId,
    PERSONA_CONFIRM_ACCEPT,
  );
  if (!result.confirmed) {
    return false;
  }
  const marked = await markPersonaInboxEventsAsRead(alertId, inboxEventId);
  dispatchInboxChanged({ eventIds: marked, alertId });
  return true;
}
