import type { TFunction } from "i18next";

export function getPersonaDriftTitle(
  t: TFunction,
  provenance?: string,
): string {
  if (provenance === "startup_scan") {
    return t("security.integrityProtection.personaDriftAlertTitleStartup");
  }
  return t("security.integrityProtection.personaDriftAlertTitle");
}

export function getPersonaDriftBody(t: TFunction, path: string): string {
  return t("security.integrityProtection.personaDriftAlertBody", { path });
}

export function getPersonaProtectionChannelName(t: TFunction): string {
  return t("security.integrityProtection.personaProtectionChannel");
}
