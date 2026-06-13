import { Button } from "@agentscope-ai/design";
import { useTranslation } from "react-i18next";
import type { ToolGuardRulesIntegrity } from "../api/client";
import styles from "@/pages/Settings/Security/index.module.less";

interface RuleIntegrityRepairBannerProps {
  rulesIntegrity: ToolGuardRulesIntegrity | null;
  repairing: boolean;
  onRepair: () => void;
}

export function RuleIntegrityRepairBanner({
  rulesIntegrity,
  repairing,
  onRepair,
}: RuleIntegrityRepairBannerProps) {
  const { t } = useTranslation();

  if (!rulesIntegrity || rulesIntegrity.ok) {
    return null;
  }

  return (
    <div className={styles.integrityAlert}>
      <div className={styles.integrityAlertMain}>
        <span className={styles.integrityAlertIcon}>!</span>
        <span className={styles.integrityAlertTitle}>
          {t("security.rulesIntegrity.tamperedTitle", {
            defaultValue: "内置检测规则已被篡改",
          })}
        </span>
      </div>
      <Button
        danger
        type="primary"
        loading={repairing}
        onClick={onRepair}
        className={styles.integrityRepairButton}
      >
        {t("security.rulesIntegrity.repairButton", {
          defaultValue: "修复",
        })}
      </Button>
    </div>
  );
}
