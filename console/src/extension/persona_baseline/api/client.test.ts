import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { securityApi } from "@/api/modules/security";

vi.mock("@/api/request", () => ({
  request: vi.fn(),
}));

vi.mock("@/api/config", () => ({
  getApiUrl: (path: string) => `/api${path}`,
}));

import { request } from "@/api/request";

describe("securityApi persona protection", () => {
  beforeEach(() => {
    vi.mocked(request).mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("getPersonaProtectionSettings calls settings endpoint", async () => {
    await securityApi.getPersonaProtectionSettings();
    expect(request).toHaveBeenCalledWith(
      "/config/security/persona-protection/settings",
    );
  });

  it("updatePersonaProtectionSettings sends PUT with enabled flag", async () => {
    await securityApi.updatePersonaProtectionSettings({ enabled: true });
    expect(request).toHaveBeenCalledWith(
      "/config/security/persona-protection/settings",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ enabled: true }),
      }),
    );
  });

  it("updatePersonaProtectionSettings includes confirmation phrase when re-enabling", async () => {
    await securityApi.updatePersonaProtectionSettings({
      enabled: true,
      confirmation_phrase: "Confirm re-establish persona baseline",
    });
    expect(request).toHaveBeenCalledWith(
      "/config/security/persona-protection/settings",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          enabled: true,
          confirmation_phrase: "Confirm re-establish persona baseline",
        }),
      }),
    );
  });

  it("getPersonaProtectionAlerts calls alerts endpoint", async () => {
    await securityApi.getPersonaProtectionAlerts();
    expect(request).toHaveBeenCalledWith(
      "/config/security/persona-protection/alerts",
    );
  });

  it("restorePersonaProtectionAlert posts alert id and confirmation phrase", async () => {
    await securityApi.restorePersonaProtectionAlert(
      "alert-123",
      "Confirm persona restore",
    );
    expect(request).toHaveBeenCalledWith(
      "/config/security/persona-protection/restore",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          alert_id: "alert-123",
          confirmation_phrase: "Confirm persona restore",
        }),
      }),
    );
  });

  it("acceptPersonaProtectionAlert posts alert id and confirmation phrase", async () => {
    await securityApi.acceptPersonaProtectionAlert(
      "alert-456",
      "Confirm persona accept",
    );
    expect(request).toHaveBeenCalledWith(
      "/config/security/persona-protection/accept",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          alert_id: "alert-456",
          confirmation_phrase: "Confirm persona accept",
        }),
      }),
    );
  });

  it("getPersonaProtectionWatchUrl returns SSE watch path", () => {
    expect(securityApi.getPersonaProtectionWatchUrl()).toBe(
      "/api/config/security/persona-protection/watch",
    );
  });
});
