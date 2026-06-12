export { IntegrityCheckPersonaFrame } from "./components/IntegrityCheckPersonaFrame";
export { default as PersonaDriftAlertNotifier } from "./components/PersonaDriftAlertNotifier";
export {
  PersonaProtectionAlertsCard,
  PersonaProtectionProtectedPaths,
  PersonaProtectionProvider,
  PersonaProtectionSwitchRow,
  usePersonaProtectionContext,
} from "./components/PersonaProtectionSection";
export { usePersonaDriftWatch } from "./hooks/usePersonaDriftWatch";
export type {
  PersonaAlertResolvedEvent,
  PersonaBaselineUpdatedEvent,
  PersonaDriftEvent,
  PersonaProtectionEvent,
} from "./hooks/usePersonaDriftWatch";
export {
  personaApi,
  type PersonaProtectionActionResponse,
  type PersonaProtectionAlert,
  type PersonaProtectionAlertsResponse,
  type PersonaProtectionSettings,
  type PersonaProtectionSettingsUpdateBody,
} from "./api/client";
export {
  acceptPersonaAlert,
  collectUnreadPersonaInboxEventIds,
  markPersonaInboxEventsAsRead,
  markPersonaInboxReadByAlertId,
  PERSONA_CONFIRM_ACCEPT,
  PERSONA_CONFIRM_RESTORE,
  restorePersonaAlert,
} from "./lib/alertActions";
export {
  getPersonaDriftBody,
  getPersonaDriftTitle,
  getPersonaProtectionChannelName,
} from "./lib/driftDisplay";
export {
  mapInboxEventsByAlertId,
  mergeAlertItems,
  type PersonaDriftAlertCopy,
  type PersonaDriftAlertItem,
} from "./lib/driftAlertItems";
export {
  resolvePersonaDriftDeepLink,
  resolvePersonaDriftNavigation,
} from "./lib/navigation";
