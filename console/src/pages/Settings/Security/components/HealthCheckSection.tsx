import { useEffect, useMemo, useState } from "react";
import { Button, Card, Input, Progress, Table, Tag } from "@agentscope-ai/design";
import { Space } from "antd";
import { useTranslation } from "react-i18next";
import api from "../../../../api";
import type {
  HealthCheckFixResponse,
  HealthCheckItem,
  HealthCheckScanResponse,
} from "../../../../api/modules/security";
import styles from "../index.module.less";

const CONFIRMATION_PHRASE_KEY = "security.healthCheck.confirmationPhrase";
const CAROUSEL_DISPLAY_DURATION_MS = 1800;
const TERMINAL_SCAN_STATES = ["completed", "failed", "cancelled", "interrupted"];
const TERMINAL_CAROUSEL_KEYS: Record<string, string> = {
  completed: "security.healthCheck.carousel.completed",
  failed: "security.healthCheck.carousel.failed",
  cancelled: "security.healthCheck.carousel.cancelled",
  interrupted: "security.healthCheck.carousel.interrupted",
};

type HealthCheckRecord = Record<string, unknown>;

function getString(record: HealthCheckRecord | HealthCheckItem | undefined, key: string): string {
  const value = (record as HealthCheckRecord | undefined)?.[key];
  return typeof value === "string" ? value : "";
}

export function HealthCheckSection() {
  const { t } = useTranslation();
  const [scan, setScan] = useState<HealthCheckScanResponse | null>(null);
  const [fixResult, setFixResult] = useState<HealthCheckFixResponse | null>(
    null,
  );
  const [confirmation, setConfirmation] = useState("");
  const [loading, setLoading] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [currentCheckIndex, setCurrentCheckIndex] = useState(0);
  const confirmationPhrase = t(CONFIRMATION_PHRASE_KEY);

  const runScan = async (deep: boolean = false) => {
    setLoading(true);
    setScanError(null);
    setCurrentCheckIndex(0);
    try {
      setScan(await api.runIntegrityHealthCheckScan(deep));
      setFixResult(null);
    } catch (error) {
      setScanError(error instanceof Error ? error.message : t("security.healthCheck.loadFailed"));
    } finally {
      setLoading(false);
    }
  };

  const checkItemIds = useMemo(() => {
    return (
      scan?.check_items
        ?.filter((item) => !item.deep_only || item.status !== "skipped")
        .map((item) => item.id)
        .filter(Boolean) ?? []
    );
  }, [scan]);

  const currentCheckId =
    checkItemIds[currentCheckIndex % Math.max(checkItemIds.length, 1)] ?? "";
  const scanStatus = loading ? "running" : scanError ? "failed" : scan ? "completed" : null;
  const isTerminalState =
    scanStatus !== null && TERMINAL_SCAN_STATES.includes(scanStatus);
  const currentCheck = loading
    ? t("security.healthCheck.carousel.currentPrefix", {
        item: currentCheckId
          ? t(`security.healthCheck.scanItems.${currentCheckId}`)
          : t("security.healthCheck.carousel.idle"),
      })
    : scanStatus
      ? t(
          TERMINAL_CAROUSEL_KEYS[scanStatus] ??
            "security.healthCheck.carousel.idle",
        )
      : t("security.healthCheck.carousel.idle");

  useEffect(() => {
    if (!loading || checkItemIds.length < 2) {
      return undefined;
    }
    const carousel = window.setInterval(() => {
      setCurrentCheckIndex((index) => (index + 1) % checkItemIds.length);
    }, CAROUSEL_DISPLAY_DURATION_MS);
    return () => {
      window.clearInterval(carousel);
    };
  }, [checkItemIds.length, loading]);

  useEffect(() => {
    if (isTerminalState) {
      setCurrentCheckIndex(0);
    }
  }, [isTerminalState]);

  const selectedRepair =
    scan?.repair_suggestions?.[0]?.label ||
    "repair_missing_console_static_build";
  const selectedRepairLabel = t(`security.healthCheck.repairs.${selectedRepair}`, {
    defaultValue: selectedRepair,
  });

  const runConfirmedFix = async () => {
    if (confirmation !== confirmationPhrase) return;
    setLoading(true);
    try {
      setFixResult(
        await api.runIntegrityHealthCheckFix(selectedRepair, confirmation),
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.sectionFileGuardContainer}>
      <Card className={styles.formCard}>
        <div className={styles.sectionHeader}>
          <h3 className={styles.sectionTitle}>{t("security.healthCheck.title")}</h3>
          <Space>
            <Button type="primary" loading={loading} onClick={() => runScan(false)}>
              {t("security.healthCheck.runReadOnlyScan")}
            </Button>
            <Button loading={loading} onClick={() => runScan(true)}>
              {t("security.healthCheck.runDeepScan")}
            </Button>
          </Space>
        </div>
        <p className={styles.tabDescription}>
          {t("security.healthCheck.scanOnlyNotice")}
        </p>
        <Progress percent={loading ? Math.max(scan?.progress ?? 0, 15) : scan?.progress ?? 0} />
        <div className={styles.integrityResult} data-terminal={isTerminalState}>
          <Tag color={loading ? "blue" : scanError ? "red" : scan ? "green" : "default"}>
            {scanStatus
              ? t(`security.healthCheck.status.${scanStatus}`)
              : t("security.healthCheck.status.idle")}
          </Tag>
          <span>{currentCheck}</span>
        </div>
        {scan && (
          <div className={styles.integrityResult}>
            <Tag color={scan.read_only ? "green" : "red"}>
              {scan.read_only
                ? t("security.healthCheck.status.readOnlyScan")
                : t("security.healthCheck.status.mutatingScan")}
            </Tag>
            <span>{scan.scan_id}</span>
          </div>
        )}
        {scanError && (
          <div className={styles.integrityResult}>
            <Tag color="red">{t("security.healthCheck.status.failed")}</Tag>
            <span>{scanError}</span>
          </div>
        )}
      </Card>

      <Card className={styles.tableCard}>
        <Table
          rowKey={(record) => String(record.id)}
          dataSource={scan?.check_items ?? []}
          pagination={false}
          size="small"
          locale={{ emptyText: t("security.healthCheck.emptyCheckItems") }}
          columns={[
            {
              title: t("security.healthCheck.columns.group"),
              dataIndex: "group",
              key: "group",
              render: (group: string) => (
                <Tag color="blue">
                  {t(`security.healthCheck.groups.${group}`, {
                    defaultValue: group,
                  })}
                </Tag>
              ),
            },
            {
              title: t("security.healthCheck.columns.check"),
              dataIndex: "label",
              key: "label",
              render: (_label: string, record: HealthCheckRecord) =>
                t(`security.healthCheck.scanItems.${getString(record, "id")}`, {
                  defaultValue: getString(record, "label"),
                }),
            },
            {
              title: t("security.healthCheck.columns.status"),
              dataIndex: "status",
              key: "status",
              render: (status: string) => (
                <Tag color={status === "ok" ? "green" : "orange"}>
                  {t(`security.healthCheck.itemStatus.${status}`, {
                    defaultValue: status,
                  })}
                </Tag>
              ),
            },
            {
              title: t("security.healthCheck.columns.detail"),
              dataIndex: "detail",
              key: "detail",
            },
            {
              title: t("security.healthCheck.columns.risk"),
              dataIndex: "risk",
              key: "risk",
              render: (risk: string, record: HealthCheckRecord) =>
                risk || getString(record, "recommendation") || "-",
            },
            {
              title: t("security.healthCheck.columns.fixId"),
              dataIndex: "fix_id",
              key: "fix_id",
              render: (fixId: string | null | undefined) => fixId || "-",
            },
          ]}
        />
      </Card>

      {scan && (
        <Card className={styles.formCard}>
          <Space direction="vertical" style={{ width: "100%" }}>
            <span className={styles.skillScannerLabel}>
              {t("security.healthCheck.selectedRepair", {
                repair: selectedRepairLabel,
              })}
            </span>
            <span className={styles.tabDescription}>
              {t("security.healthCheck.risks.title")}:{" "}
              {scan.risk_summary.length
                ? scan.risk_summary.join(", ")
                : t("security.healthCheck.noRisks")}
            </span>
            <span className={styles.tabDescription}>
              {t("security.healthCheck.repairs.title")}
            </span>
            <Input
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              placeholder={confirmationPhrase}
              allowClear
            />
            <Button
              danger
              loading={loading}
              disabled={confirmation !== confirmationPhrase}
              onClick={runConfirmedFix}
            >
              {t("security.healthCheck.confirmSelectedDoctorFix")}
            </Button>
            {fixResult && (
              <div className={styles.integrityResult}>
                <Tag color={fixResult.exit_code === 0 ? "green" : "red"}>
                  {fixResult.executed
                    ? t("security.healthCheck.fixResult.executed")
                    : t("security.healthCheck.fixResult.notExecuted")}
                </Tag>
                <span>
                  {t("security.healthCheck.fixResult.doctorFixId", {
                    fixId: fixResult.fix_id,
                  })}
                </span>
              </div>
            )}
          </Space>
        </Card>
      )}
    </div>
  );
}
