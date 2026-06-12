# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from .security_event_harness import (
    InvalidSecurityEventScenario,
    SecurityEventIngestionHarness,
    SecurityEventSubmission,
)


def _endpoint_edr_event(event_id: str, **overrides) -> SecurityEventSubmission:
    base = {
        "source_system": "endpoint_edr",
        "event_id": event_id,
        "event_type_id": "malware_detected",
        "schema_version": "1.0",
        "severity": "HIGH",
        "summary": "Endpoint malware blocked on finance workstation",
        "occurred_at": "2026-06-12T03:00:00Z",
        "payload": {
            "assetId": "finance-workstation-7",
            "detectionName": "EICAR-Test-File",
            "actionTaken": "blocked",
        },
    }
    base.update(overrides)
    return SecurityEventSubmission(**base)


@pytest.mark.integration
@pytest.mark.p0
def test_accepts_legal_event_after_persistence(app_server) -> None:
    """Control point: submit one legal configured security event and read it back.

    Observation point: success only follows persistence; list/detail visibility and
    backend-generated receivedAt prove the accepted event is durable and operator-visible.
    """

    harness = SecurityEventIngestionHarness.for_app_server(app_server)

    # // GIVEN
    legal_endpoint_event = _endpoint_edr_event(
        "edr-legal-event-001",
        caller_supplied_received_at="1999-01-01T00:00:00Z",
    )

    # // WHEN
    accepted_event_observation = harness.accept_legal_event_after_persistence(
        legal_endpoint_event,
    )

    # // THEN
    assert accepted_event_observation.is_ready(), accepted_event_observation.render_failure_report()


@pytest.mark.integration
@pytest.mark.p0
def test_rejects_invalid_event_config_boundary(app_server) -> None:
    """Control point: submit source, type, schema, and payload violations.

    Observation point: each rejection is readable, absent from accepted events,
    and preserved as a bounded failed reception record.
    """

    harness = SecurityEventIngestionHarness.for_app_server(app_server)

    # // GIVEN
    invalid_config_scenarios = (
        InvalidSecurityEventScenario(
            business_label="unknown source system",
            submission=_endpoint_edr_event("invalid-source-001", source_system="unknown_scanner"),
            expected_failure_reason="SOURCE_SYSTEM_NOT_ALLOWED",
        ),
        InvalidSecurityEventScenario(
            business_label="disabled source system",
            submission=_endpoint_edr_event("disabled-source-001", source_system="retired_dlp"),
            expected_failure_reason="SOURCE_SYSTEM_DISABLED",
        ),
        InvalidSecurityEventScenario(
            business_label="event type not authorized for source",
            submission=_endpoint_edr_event("unauthorized-type-001", event_type_id="mailbox_forward_rule_created"),
            expected_failure_reason="EVENT_TYPE_NOT_ALLOWED_FOR_SOURCE",
        ),
        InvalidSecurityEventScenario(
            business_label="unknown event type",
            submission=_endpoint_edr_event("unknown-event-type-001", event_type_id="nonexistent_security_event_type"),
            expected_failure_reason="EVENT_TYPE_NOT_FOUND",
        ),
        InvalidSecurityEventScenario(
            business_label="unknown schema version",
            submission=_endpoint_edr_event("unknown-schema-001", schema_version="9.9"),
            expected_failure_reason="SCHEMA_VERSION_NOT_FOUND",
        ),
        InvalidSecurityEventScenario(
            business_label="base required summary missing",
            submission=_endpoint_edr_event(
                "missing-base-summary-001",
                omitted_request_fields=("summary",),
            ),
            expected_failure_reason="BASE_REQUIRED_FIELD_MISSING",
        ),
        InvalidSecurityEventScenario(
            business_label="required payload field missing",
            submission=_endpoint_edr_event(
                "missing-payload-field-001",
                payload={"assetId": "finance-workstation-7", "actionTaken": "blocked"},
            ),
            expected_failure_reason="PAYLOAD_REQUIRED_FIELD_MISSING",
        ),
        InvalidSecurityEventScenario(
            business_label="payload field type invalid",
            submission=_endpoint_edr_event(
                "invalid-payload-type-001",
                payload={
                    "assetId": 404,
                    "detectionName": "EICAR-Test-File",
                    "actionTaken": "blocked",
                },
            ),
            expected_failure_reason="PAYLOAD_FIELD_TYPE_INVALID",
        ),
        InvalidSecurityEventScenario(
            business_label="payload enum field invalid",
            submission=_endpoint_edr_event(
                "invalid-payload-enum-001",
                payload={
                    "assetId": "finance-workstation-7",
                    "detectionName": "EICAR-Test-File",
                    "actionTaken": "silently_ignored",
                },
            ),
            expected_failure_reason="PAYLOAD_ENUM_VALUE_INVALID",
        ),
    )

    # // WHEN
    rejection_observation = harness.reject_invalid_event_config_boundary(
        invalid_config_scenarios,
    )

    # // THEN
    assert rejection_observation.is_ready(), rejection_observation.render_failure_report()


@pytest.mark.integration
@pytest.mark.p0
def test_preserves_undefined_payload_fields_in_detail_only(app_server) -> None:
    """Control point: submit a legal event with one extra undefined payload field.

    Observation point: the undefined field is preserved for traceability, but it is
    excluded from primary list columns and separated in the detail view.
    """

    harness = SecurityEventIngestionHarness.for_app_server(app_server)

    # // GIVEN
    event_with_undefined_field = _endpoint_edr_event(
        "undefined-field-001",
        payload={
            "assetId": "finance-workstation-7",
            "detectionName": "EICAR-Test-File",
            "actionTaken": "blocked",
            "collectorBuildFingerprint": "agent-build-2026-06-12",
        },
    )

    # // WHEN
    undefined_field_observation = harness.preserve_undefined_payload_fields_in_detail_only(
        event_with_undefined_field,
        configured_field_name="assetId",
        undefined_field_name="collectorBuildFingerprint",
    )

    # // THEN
    assert undefined_field_observation.is_ready(), undefined_field_observation.render_failure_report()


@pytest.mark.integration
@pytest.mark.p0
def test_enforces_source_event_id_idempotency(app_server) -> None:
    """Control point: repeat an event, conflict on the same key, then reuse eventId
    from a different source system.

    Observation point: sourceSystem plus eventId is the idempotency key; identical
    repeats do not duplicate and conflicting same-key writes are rejected.
    """

    harness = SecurityEventIngestionHarness.for_app_server(app_server)

    # // GIVEN
    original_endpoint_event = _endpoint_edr_event("idempotent-event-001")
    conflicting_endpoint_event = _endpoint_edr_event(
        "idempotent-event-001",
        payload={
            "assetId": "finance-workstation-7",
            "detectionName": "Different-Malware-Family",
            "actionTaken": "quarantined",
        },
    )
    same_event_id_from_different_source = _endpoint_edr_event(
        "idempotent-event-001",
        source_system="cloud_siem",
        event_type_id="correlation_rule_match",
        payload={
            "ruleId": "rule-high-risk-login",
            "assetId": "finance-workstation-7",
            "actionTaken": "opened_investigation",
        },
    )

    # // WHEN
    idempotency_observation = harness.enforce_source_event_id_idempotency(
        original_endpoint_event,
        conflicting_endpoint_event,
        same_event_id_from_different_source,
    )

    # // THEN
    assert idempotency_observation.is_ready(), idempotency_observation.render_failure_report()


@pytest.mark.integration
@pytest.mark.p0
def test_records_failed_receptions_without_business_event_pollution(app_server) -> None:
    """Control point: submit illegal events, a persistence-failure case, and an
    oversized illegal payload.

    Observation point: failure records remain traceable and bounded, while the
    accepted business event list stays clean.
    """

    harness = SecurityEventIngestionHarness.for_app_server(app_server)

    # // GIVEN
    illegal_reception_scenarios = (
        InvalidSecurityEventScenario(
            business_label="disallowed source",
            submission=_endpoint_edr_event("failed-disallowed-source-001", source_system="unknown_scanner"),
            expected_failure_reason="SOURCE_SYSTEM_NOT_ALLOWED",
        ),
        InvalidSecurityEventScenario(
            business_label="disallowed type",
            submission=_endpoint_edr_event("failed-disallowed-type-001", event_type_id="mailbox_forward_rule_created"),
            expected_failure_reason="EVENT_TYPE_NOT_ALLOWED_FOR_SOURCE",
        ),
        InvalidSecurityEventScenario(
            business_label="schema failure",
            submission=_endpoint_edr_event("failed-schema-001", schema_version="9.9"),
            expected_failure_reason="SCHEMA_VERSION_NOT_FOUND",
        ),
        InvalidSecurityEventScenario(
            business_label="payload validation failure",
            submission=_endpoint_edr_event("failed-payload-001", payload={"assetId": "finance-workstation-7"}),
            expected_failure_reason="PAYLOAD_REQUIRED_FIELD_MISSING",
        ),
    )
    idempotency_baseline_event = _endpoint_edr_event("failed-idempotency-conflict-001")
    idempotency_conflict_event = _endpoint_edr_event(
        "failed-idempotency-conflict-001",
        payload={
            "assetId": "finance-workstation-7",
            "detectionName": "Different-Malware-Family",
            "actionTaken": "quarantined",
        },
    )
    persistence_error_event = _endpoint_edr_event("failed-persistence-001")
    oversized_illegal_payload_event = _endpoint_edr_event(
        "failed-oversized-payload-001",
        source_system="unknown_scanner",
        payload={
            "assetId": "finance-workstation-7",
            "oversizedDiagnosticBlob": "x" * 20000,
        },
    )

    # // WHEN
    failed_reception_observation = harness.record_failed_receptions_without_business_event_pollution(
        illegal_reception_scenarios,
        idempotency_baseline_event,
        idempotency_conflict_event,
        persistence_error_event,
        oversized_illegal_payload_event,
    )

    # // THEN
    assert failed_reception_observation.is_ready(), failed_reception_observation.render_failure_report()
