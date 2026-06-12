import { describe, it, expect } from "vitest";
import {
  resolvePersonaDriftDeepLink,
  resolvePersonaDriftNavigation,
} from "./navigation";

describe("personaNavigation", () => {
  it("prefers payload deep_link when present", () => {
    expect(
      resolvePersonaDriftDeepLink({
        deep_link:
          "/security?tab=integrityCheck&personaAlertId=alert-from-inbox",
        alert_id: "alert-from-inbox",
      }),
    ).toBe("/security?tab=integrityCheck&personaAlertId=alert-from-inbox");
  });

  it("builds integrity check link from alert_id fallback", () => {
    expect(
      resolvePersonaDriftDeepLink({
        alert_id: "alert-xyz",
      }),
    ).toBe("/security?tab=integrityCheck&personaAlertId=alert-xyz");
  });

  it("returns null for non-persona events", () => {
    expect(
      resolvePersonaDriftNavigation("heartbeat", {
        alert_id: "ignored",
      }),
    ).toBeNull();
  });

  it("returns deep link for persona_drift event type", () => {
    expect(
      resolvePersonaDriftNavigation("persona_drift", {
        deep_link:
          "/security?tab=integrityCheck&personaAlertId=alert-from-inbox",
      }),
    ).toBe("/security?tab=integrityCheck&personaAlertId=alert-from-inbox");
  });
});
