# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from tests.integration.security.security_event_harness import (
    SecurityEventIngestionHarness,
    SecurityEventSubmission,
)


def _event_for_inbox(
    event_id: str,
    *,
    source_system: str,
    event_type_id: str,
    severity: str,
    occurred_at: str,
    asset_id: str,
    summary: str,
) -> SecurityEventSubmission:
    return SecurityEventSubmission(
        source_system=source_system,
        event_id=event_id,
        event_type_id=event_type_id,
        schema_version="1.0",
        severity=severity,
        summary=summary,
        occurred_at=occurred_at,
        payload={
            "assetId": asset_id,
            "detectionName": "Inbox Contract Probe",
            "actionTaken": "blocked",
            "collectorBuildFingerprint": f"build-for-{event_id}",
        },
    )


@pytest.mark.integration
@pytest.mark.p0
def test_web_lists_filters_and_opens_event_detail(app_server) -> None:
    """Control point: seed accepted events, open the operator Web inbox, apply
    source/type/severity/time filters, and navigate to a stable detail URL.

    Observation point: list ordering, filter correctness, event type display name,
    configured list payload fields, detail base facts, structured payload,
    undefined fields, and bounded raw payload are visible through the Web/API
    inbox contract.
    """

    harness = SecurityEventIngestionHarness.for_app_server(app_server)

    # // GIVEN
    inbox_events = (
        _event_for_inbox(
            "web-inbox-high-001",
            source_system="endpoint_edr",
            event_type_id="malware_detected",
            severity="HIGH",
            occurred_at="2026-06-12T03:10:00Z",
            asset_id="finance-workstation-7",
            summary="High severity malware event for inbox list",
        ),
        _event_for_inbox(
            "web-inbox-medium-001",
            source_system="cloud_siem",
            event_type_id="correlation_rule_match",
            severity="MEDIUM",
            occurred_at="2026-06-12T03:05:00Z",
            asset_id="identity-provider",
            summary="Medium severity SIEM correlation event",
        ),
    )

    # // WHEN
    web_inbox_observation = harness.web_lists_filters_and_opens_event_detail(
        inbox_events,
    )

    # // THEN
    assert web_inbox_observation.is_ready(), web_inbox_observation.render_failure_report()
