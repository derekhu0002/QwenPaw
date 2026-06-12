export const INBOX_CHANGED_EVENT = "qwenpaw:inbox-changed";

export interface InboxChangedDetail {
  eventIds?: string[];
  alertId?: string;
}

export function dispatchInboxChanged(detail?: InboxChangedDetail): void {
  window.dispatchEvent(new CustomEvent(INBOX_CHANGED_EVENT, { detail }));
}

export function readInboxChangedDetail(event: Event): InboxChangedDetail | undefined {
  if (!(event instanceof CustomEvent)) {
    return undefined;
  }
  const detail = event.detail;
  if (!detail || typeof detail !== "object") {
    return undefined;
  }
  return detail as InboxChangedDetail;
}
