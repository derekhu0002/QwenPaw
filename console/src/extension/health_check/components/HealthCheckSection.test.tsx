import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/common_setup";
import { HealthCheckSection } from "./HealthCheckSection";
import type { HealthCheckScanResponse } from "@/api/modules/security";

const { mockRunScan, mockRunFix } = vi.hoisted(() => ({
  mockRunScan: vi.fn(),
  mockRunFix: vi.fn(),
}));

vi.mock("@/api", () => ({
  default: {
    runIntegrityHealthCheckScan: mockRunScan,
    runIntegrityHealthCheckFix: mockRunFix,
  },
}));

vi.mock("@agentscope-ai/design", async () => {
  const antd = await import("antd");
  return {
    Button: antd.Button,
    Card: antd.Card,
    Input: antd.Input,
    Table: antd.Table,
    Tag: antd.Tag,
    Progress: antd.Progress,
  };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string; repair?: string; item?: string; fixId?: string }) => {
      const labels: Record<string, string> = {
        "security.healthCheck.title": "Health Check",
        "security.healthCheck.runReadOnlyScan": "Run read-only scan",
        "security.healthCheck.runDeepScan": "Run deep connectivity scan",
        "security.healthCheck.scanOnlyNotice": "Scan-only notice",
        "security.healthCheck.status.idle": "Idle",
        "security.healthCheck.status.running": "Running",
        "security.healthCheck.status.completed": "Completed",
        "security.healthCheck.status.readOnlyScan": "Read-only scan",
        "security.healthCheck.status.failed": "Failed",
        "security.healthCheck.carousel.idle": "Waiting",
        "security.healthCheck.carousel.currentPrefix": "Checking {{item}}",
        "security.healthCheck.carousel.completed": "Scan completed",
        "security.healthCheck.emptyCheckItems": "No health check items yet",
        "security.healthCheck.loadFailed": "Failed to run health check scan",
        "security.healthCheck.columns.group": "Group",
        "security.healthCheck.columns.check": "Check",
        "security.healthCheck.columns.status": "Status",
        "security.healthCheck.columns.detail": "Detail",
        "security.healthCheck.columns.risk": "Risk",
        "security.healthCheck.columns.fixId": "Fix ID",
        "security.healthCheck.scanItems.working-dir": "Working directory",
        "security.healthCheck.groups.environment": "Environment",
        "security.healthCheck.itemStatus.ok": "OK",
        "security.healthCheck.selectedRepair": "Selected repair: {{repair}}",
        "security.healthCheck.risks.title": "Risks",
        "security.healthCheck.noRisks": "No risks",
        "security.healthCheck.repairs.title": "Repairs",
        "security.healthCheck.confirmationPhrase": "Confirm selected doctor fix",
        "security.healthCheck.confirmSelectedDoctorFix": "Confirm selected doctor fix",
        "security.healthCheck.repairs.repair_missing_console_static_build":
          "Repair console static build",
        "security.healthCheck.fixResult.executed": "Fix executed",
        "security.healthCheck.fixResult.notExecuted": "Fix not executed",
        "security.healthCheck.fixResult.doctorFixId": "Doctor fix: {{fixId}}",
      };
      if (key === "security.healthCheck.selectedRepair" && options?.repair) {
        return `Selected repair: ${options.repair}`;
      }
      if (key === "security.healthCheck.carousel.currentPrefix" && options?.item) {
        return `Checking ${options.item}`;
      }
      return labels[key] ?? options?.defaultValue ?? key;
    },
  }),
}));

const sampleScan: HealthCheckScanResponse = {
  scan_id: "health-scan-test",
  read_only: true,
  progress: 100,
  check_items: [
    {
      id: "working-dir",
      group: "environment",
      label: "Working directory",
      status: "ok",
      detail: "exists",
      risk: "",
      recommendation: "",
      fix_id: null,
      deep_only: false,
    },
  ],
  risk_summary: [],
  repair_suggestions: [
    {
      label: "repair_missing_console_static_build",
      doctor_fix_id: "static-build",
      requires_confirmation: true,
    },
  ],
  mutated_files: [],
};

describe("HealthCheckSection", () => {
  beforeEach(() => {
    mockRunScan.mockResolvedValue(sampleScan);
    mockRunFix.mockResolvedValue({
      confirmed: true,
      selected_repair: "repair_missing_console_static_build",
      fix_id: "static-build",
      executed: true,
      exit_code: 0,
      output: ["done"],
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders scan actions", () => {
    renderWithProviders(<HealthCheckSection />);
    expect(screen.getByText("Health Check")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run read-only scan" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run deep connectivity scan" })).toBeInTheDocument();
  });

  it("runs read-only scan with deep=false (HC-S01)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<HealthCheckSection />);
    await user.click(screen.getByRole("button", { name: "Run read-only scan" }));
    await waitFor(() => {
      expect(mockRunScan).toHaveBeenCalledWith(false);
    });
  });

  it("runs deep scan with deep=true (HC-S02)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<HealthCheckSection />);
    await user.click(screen.getByRole("button", { name: "Run deep connectivity scan" }));
    await waitFor(() => {
      expect(mockRunScan).toHaveBeenCalledWith(true);
    });
  });

  it("shows grouped check items after scan (HC-S03)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<HealthCheckSection />);
    await user.click(screen.getByRole("button", { name: "Run read-only scan" }));
    await waitFor(() => {
      expect(screen.getByText("Working directory")).toBeInTheDocument();
    });
    expect(screen.getByText("Environment")).toBeInTheDocument();
  });

  it("requires confirmation phrase before running doctor fix (HC-S04)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<HealthCheckSection />);
    await user.click(screen.getByRole("button", { name: "Run read-only scan" }));
    await waitFor(() => {
      expect(screen.getByPlaceholderText("Confirm selected doctor fix")).toBeInTheDocument();
    });
    const fixButton = screen.getByRole("button", { name: "Confirm selected doctor fix" });
    expect(fixButton).toBeDisabled();
    await user.type(
      screen.getByPlaceholderText("Confirm selected doctor fix"),
      "Confirm selected doctor fix",
    );
    expect(fixButton).not.toBeDisabled();
  });

  it("submits confirmed doctor fix after phrase match (HC-S05)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<HealthCheckSection />);
    await user.click(screen.getByRole("button", { name: "Run read-only scan" }));
    await waitFor(() => {
      expect(screen.getByPlaceholderText("Confirm selected doctor fix")).toBeInTheDocument();
    });
    await user.type(
      screen.getByPlaceholderText("Confirm selected doctor fix"),
      "Confirm selected doctor fix",
    );
    await user.click(screen.getByRole("button", { name: "Confirm selected doctor fix" }));
    await waitFor(() => {
      expect(mockRunFix).toHaveBeenCalledWith(
        "repair_missing_console_static_build",
        "Confirm selected doctor fix",
      );
    });
    expect(screen.getByText("Fix executed")).toBeInTheDocument();
  });

  it("shows failure state when scan request rejects (HC-S07)", async () => {
    mockRunScan.mockRejectedValueOnce(new Error("network down"));
    const user = userEvent.setup();
    renderWithProviders(<HealthCheckSection />);
    await user.click(screen.getByRole("button", { name: "Run read-only scan" }));
    await waitFor(() => {
      expect(screen.getByText("network down")).toBeInTheDocument();
    });
  });
});
