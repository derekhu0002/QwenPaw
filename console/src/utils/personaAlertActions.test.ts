import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  acceptPersonaAlert,
  markPersonaInboxReadByAlertId,
  restorePersonaAlert,
  PERSONA_CONFIRM_ACCEPT,
  PERSONA_CONFIRM_RESTORE,
} from "./personaAlertActions";
import { INBOX_CHANGED_EVENT } from "./inboxEvents";

const mockRestore = vi.fn();
const mockAccept = vi.fn();
const mockGetInboxEvents = vi.fn();
const mockMarkInboxRead = vi.fn();

vi.mock("../api", () => ({
  default: {
    restorePersonaProtectionAlert: (...args: unknown[]) => mockRestore(...args),
    acceptPersonaProtectionAlert: (...args: unknown[]) => mockAccept(...args),
    getInboxEvents: (...args: unknown[]) => mockGetInboxEvents(...args),
    markInboxRead: (...args: unknown[]) => mockMarkInboxRead(...args),
  },
}));

describe("personaAlertActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRestore.mockResolvedValue({ confirmed: true });
    mockAccept.mockResolvedValue({ confirmed: true });
    mockMarkInboxRead.mockResolvedValue({ updated: 1 });
  });

  it("restorePersonaAlert marks inbox read and dispatches inbox changed", async () => {
    const listener = vi.fn();
    window.addEventListener(INBOX_CHANGED_EVENT, listener);

    const ok = await restorePersonaAlert("alert-1", "evt-1");

    expect(ok).toBe(true);
    expect(mockRestore).toHaveBeenCalledWith("alert-1", PERSONA_CONFIRM_RESTORE);
    expect(mockMarkInboxRead).toHaveBeenCalledWith({ event_ids: ["evt-1"] });
    expect(listener).toHaveBeenCalled();

    window.removeEventListener(INBOX_CHANGED_EVENT, listener);
  });

  it("acceptPersonaAlert resolves unread inbox event by alert id", async () => {
    mockGetInboxEvents.mockResolvedValue({
      events: [
        {
          id: "evt-2",
          source_id: "alert-2",
          event_type: "persona_drift",
          read: false,
        },
      ],
    });

    const ok = await acceptPersonaAlert("alert-2");

    expect(ok).toBe(true);
    expect(mockAccept).toHaveBeenCalledWith("alert-2", PERSONA_CONFIRM_ACCEPT);
    expect(mockMarkInboxRead).toHaveBeenCalledWith({ event_ids: ["evt-2"] });
  });

  it("markPersonaInboxReadByAlertId no-ops when no matching event", async () => {
    mockGetInboxEvents.mockResolvedValue({ events: [] });
    await markPersonaInboxReadByAlertId("missing");
    expect(mockMarkInboxRead).not.toHaveBeenCalled();
  });
});
