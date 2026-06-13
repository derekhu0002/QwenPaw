import { describe, it, expect, vi } from "vitest";
import { ruleIntegrityApi } from "./client";

vi.mock("@/api/request", () => ({
  request: vi.fn(),
}));

describe("ruleIntegrityApi", () => {
  it("calls tool guard rules integrity status endpoint", async () => {
    const { request } = await import("@/api/request");
    vi.mocked(request).mockResolvedValue({ ok: true, status: "ok", findings: [] });

    await ruleIntegrityApi.getToolGuardRulesIntegrity();

    expect(request).toHaveBeenCalledWith(
      "/config/security/tool-guard/rules-integrity",
    );
  });

  it("calls passive integrity check endpoint", async () => {
    const { request } = await import("@/api/request");
    vi.mocked(request).mockResolvedValue({ ok: true, status: "ok", findings: [] });

    await ruleIntegrityApi.checkIntegrityRuleEntry();

    expect(request).toHaveBeenCalledWith(
      "/config/security/integrity-protection/rules-integrity/check",
      { method: "POST" },
    );
  });
});
