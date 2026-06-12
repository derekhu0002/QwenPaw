export function resolvePersonaDriftDeepLink(
  payload: Record<string, unknown>,
): string | null {
  const deepLink =
    typeof payload.deep_link === "string" ? payload.deep_link : null;
  if (deepLink) {
    return deepLink;
  }
  const alertId =
    typeof payload.alert_id === "string" ? payload.alert_id : null;
  if (alertId) {
    return `/security?tab=integrityCheck&personaAlertId=${encodeURIComponent(alertId)}`;
  }
  return null;
}

export function resolvePersonaDriftNavigation(
  eventType: string | undefined,
  payload: unknown,
): string | null {
  if ((eventType || "").toLowerCase() !== "persona_drift") {
    return null;
  }
  if (!payload || typeof payload !== "object") {
    return null;
  }
  return resolvePersonaDriftDeepLink(payload as Record<string, unknown>);
}
