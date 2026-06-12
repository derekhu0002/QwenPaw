from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


_HTTP_TIMEOUT_SECONDS = 15.0
_MAX_FAILURE_SUMMARY_CHARS = 4096


@dataclass(frozen=True)
class InternalSourceSystem:
    source_system: str
    enabled: bool
    allowed_event_type_id: str


@dataclass(frozen=True)
class SecurityEventSubmission:
    source_system: str
    event_id: str
    event_type_id: str
    schema_version: str
    severity: str
    summary: str
    occurred_at: str
    payload: dict[str, Any]
    caller_supplied_received_at: str | None = None
    omitted_request_fields: tuple[str, ...] = ()

    def request_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "sourceSystem": self.source_system,
            "eventId": self.event_id,
            "eventTypeId": self.event_type_id,
            "schemaVersion": self.schema_version,
            "severity": self.severity,
            "summary": self.summary,
            "occurredAt": self.occurred_at,
            "payload": self.payload,
        }
        if self.caller_supplied_received_at is not None:
            body["receivedAt"] = self.caller_supplied_received_at
        for field_name in self.omitted_request_fields:
            body.pop(field_name, None)
        return body


@dataclass(frozen=True)
class InvalidSecurityEventScenario:
    business_label: str
    submission: SecurityEventSubmission
    expected_failure_reason: str


@dataclass(frozen=True)
class SecurityEventObservation:
    category: str
    control_point: str
    observation_point: str
    checks: dict[str, bool]
    failure_reasons: tuple[str, ...]
    diagnostic: str = ""

    def is_ready(self) -> bool:
        return all(self.checks.values()) and not self.failure_reasons

    def render_failure_report(self) -> str:
        return json.dumps(
            {
                "category": self.category,
                "control_point": self.control_point,
                "observation_point": self.observation_point,
                "checks": self.checks,
                "failure_reasons": list(self.failure_reasons),
                "diagnostic": self.diagnostic,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )


class SecurityEventIngestionHarness:
    """Business-readable harness for the Security Event Ingestion V1 contract."""

    def __init__(self, *, api_base_url: str | None, web_base_url: str | None) -> None:
        self.api_base_url = (api_base_url or "").rstrip("/")
        self.web_base_url = (web_base_url or "").rstrip("/")

    @classmethod
    def for_app_server(cls, app_server: Any) -> "SecurityEventIngestionHarness":
        return cls(
            api_base_url=getattr(app_server, "security_center_api_url", None),
            web_base_url=getattr(app_server, "security_center_web_url", None),
        )

    def accept_legal_event_after_persistence(
        self,
        submission: SecurityEventSubmission,
    ) -> SecurityEventObservation:
        submit_response = self._submit_event(submission)
        event_list = self._list_events()
        event_detail = self._event_detail(submission.source_system, submission.event_id)

        submitted_received_at = submission.caller_supplied_received_at
        detail_received_at = event_detail.payload.get("receivedAt") if event_detail.ok else None
        matching_list_event = self._find_event(
            event_list.payload.get("events", []) if event_list.ok else [],
            submission.source_system,
            submission.event_id,
        )

        return self._observation(
            category="Security_Event_Acceptance_Gap",
            control_point=(
                "Submit one legal configured internal-system security event, then "
                "query the event list and stable detail surface immediately."
            ),
            observation_point=(
                "Success is returned only after persistence; the event is visible "
                "in receivedAt-descending list and detail by sourceSystem plus eventId."
            ),
            checks={
                "submit_api_accepts_event": submit_response.status_code == 200
                and submit_response.payload.get("success") is True,
                "duplicate_flag_is_false": submit_response.payload.get("duplicate") is False,
                "event_is_visible_in_list": matching_list_event is not None,
                "detail_lookup_is_stable": event_detail.ok
                and event_detail.payload.get("eventId") == submission.event_id,
                "received_at_is_backend_generated": bool(detail_received_at)
                and detail_received_at != submitted_received_at,
            },
            responses=[submit_response, event_list, event_detail],
        )

    def reject_invalid_event_config_boundary(
        self,
        scenarios: tuple[InvalidSecurityEventScenario, ...],
    ) -> SecurityEventObservation:
        submit_responses = [self._submit_event(scenario.submission) for scenario in scenarios]
        event_list = self._list_events()
        failure_records = self._failure_records()
        visible_events = event_list.payload.get("events", []) if event_list.ok else []
        failures = failure_records.payload.get("failures", []) if failure_records.ok else []

        return self._observation(
            category="Security_Event_Rejection_Gap",
            control_point=(
                "Submit source, event-type, schema-version, required-field, type, "
                "and enum violations through the intake API."
            ),
            observation_point=(
                "Each rejected submission returns a clear reason, stays out of the "
                "business event list, and creates a bounded failure reception record."
            ),
            checks={
                "all_invalid_requests_rejected": all(
                    response.status_code in {400, 409, 422}
                    and response.payload.get("success") is not True
                    for response in submit_responses
                ),
                "failure_reasons_are_business_readable": all(
                    self._has_reason(response, scenario.expected_failure_reason)
                    for response, scenario in zip(submit_responses, scenarios)
                ),
                "business_event_list_is_clean": all(
                    self._find_event(
                        visible_events,
                        scenario.submission.source_system,
                        scenario.submission.event_id,
                    )
                    is None
                    for scenario in scenarios
                ),
                "failure_records_are_created": all(
                    self._find_failure_record(failures, scenario.submission.event_id) is not None
                    for scenario in scenarios
                ),
                "failure_summaries_are_bounded": all(
                    len(str(record.get("requestSummary", ""))) <= _MAX_FAILURE_SUMMARY_CHARS
                    for record in failures
                )
                and bool(failures),
            },
            responses=[*submit_responses, event_list, failure_records],
        )

    def preserve_undefined_payload_fields_in_detail_only(
        self,
        submission: SecurityEventSubmission,
        *,
        configured_field_name: str,
        undefined_field_name: str,
    ) -> SecurityEventObservation:
        submit_response = self._submit_event(submission)
        event_list = self._list_events()
        event_detail = self._event_detail(submission.source_system, submission.event_id)
        matching_list_event = self._find_event(
            event_list.payload.get("events", []) if event_list.ok else [],
            submission.source_system,
            submission.event_id,
        )
        structured_payload = event_detail.payload.get("structuredPayload", {})
        undefined_payload = event_detail.payload.get("undefinedPayloadFields", {})
        raw_payload = event_detail.payload.get("rawPayload", {})

        return self._observation(
            category="Security_Event_Undefined_Field_Gap",
            control_point=(
                "Submit a legal event with all configured payload fields plus one "
                "extra payload field not declared by the contract configuration."
            ),
            observation_point=(
                "Configured fields remain primary list/detail fields, while the "
                "extra field is preserved only in undefined-fields and raw-payload detail."
            ),
            checks={
                "event_is_accepted": submit_response.status_code == 200
                and submit_response.payload.get("success") is True,
                "configured_field_is_list_visible": bool(matching_list_event)
                and configured_field_name in matching_list_event,
                "undefined_field_is_not_list_visible": bool(matching_list_event)
                and undefined_field_name not in matching_list_event,
                "configured_field_is_labeled_in_detail": configured_field_name in structured_payload,
                "undefined_field_is_detail_only": undefined_field_name in undefined_payload,
                "raw_payload_preserves_undefined_field": undefined_field_name in raw_payload,
            },
            responses=[submit_response, event_list, event_detail],
        )

    def enforce_source_event_id_idempotency(
        self,
        original_submission: SecurityEventSubmission,
        conflicting_submission: SecurityEventSubmission,
        distinct_source_submission: SecurityEventSubmission,
    ) -> SecurityEventObservation:
        first_response = self._submit_event(original_submission)
        duplicate_response = self._submit_event(original_submission)
        conflict_response = self._submit_event(conflicting_submission)
        distinct_source_response = self._submit_event(distinct_source_submission)
        event_list = self._list_events()
        failure_records = self._failure_records()
        events = event_list.payload.get("events", []) if event_list.ok else []
        failures = failure_records.payload.get("failures", []) if failure_records.ok else []

        return self._observation(
            category="Security_Event_Idempotency_Gap",
            control_point=(
                "Submit the same normalized sourceSystem plus eventId twice, then "
                "reuse that key with conflicting content, and finally reuse eventId "
                "from a different sourceSystem."
            ),
            observation_point=(
                "Identical repeat is duplicate=true without a second event; conflict "
                "is rejected and recorded; different sourceSystem is accepted."
            ),
            checks={
                "first_submission_accepted": first_response.status_code == 200
                and first_response.payload.get("success") is True,
                "identical_repeat_is_duplicate": duplicate_response.status_code == 200
                and duplicate_response.payload.get("duplicate") is True,
                "no_second_business_event_for_duplicate": self._count_events(
                    events,
                    original_submission.source_system,
                    original_submission.event_id,
                )
                == 1,
                "conflicting_same_key_is_rejected": conflict_response.status_code in {400, 409},
                "idempotency_conflict_recorded": self._find_failure_record(
                    failures,
                    conflicting_submission.event_id,
                )
                is not None,
                "same_event_id_from_different_source_is_distinct": distinct_source_response.status_code == 200
                and distinct_source_response.payload.get("success") is True,
            },
            responses=[
                first_response,
                duplicate_response,
                conflict_response,
                distinct_source_response,
                event_list,
                failure_records,
            ],
        )

    def record_failed_receptions_without_business_event_pollution(
        self,
        illegal_scenarios: tuple[InvalidSecurityEventScenario, ...],
        idempotency_original_submission: SecurityEventSubmission,
        idempotency_conflict_submission: SecurityEventSubmission,
        persistence_error_submission: SecurityEventSubmission,
        oversized_illegal_submission: SecurityEventSubmission,
    ) -> SecurityEventObservation:
        invalid_responses = [self._submit_event(scenario.submission) for scenario in illegal_scenarios]
        idempotency_original_response = self._submit_event(idempotency_original_submission)
        idempotency_conflict_response = self._submit_event(idempotency_conflict_submission)
        persistence_response = self._submit_event(
            persistence_error_submission,
            headers={"X-QwenPaw-Test-Persistence-Failure": "true"},
        )
        oversized_response = self._submit_event(oversized_illegal_submission)
        event_list = self._list_events()
        failure_records = self._failure_records()
        events = event_list.payload.get("events", []) if event_list.ok else []
        failures = failure_records.payload.get("failures", []) if failure_records.ok else []
        expected_failed_event_ids = tuple(
            scenario.submission.event_id for scenario in illegal_scenarios
        ) + (
            idempotency_conflict_submission.event_id,
            persistence_error_submission.event_id,
            oversized_illegal_submission.event_id,
        )

        return self._observation(
            category="Security_Event_Failure_Record_Gap",
            control_point=(
                "Submit illegal source/type/schema/payload cases, first create a "
                "legal idempotency baseline and then submit a conflicting same-key "
                "event, inject a test-only persistence failure, and submit an oversized "
                "illegal payload."
            ),
            observation_point=(
                "Illegal submissions never pollute business events; failure records "
                "are queryable and bounded for every failed branch; persistence failure "
                "returns failure and does not enter the business event list."
            ),
            checks={
                "illegal_requests_rejected": all(response.status_code in {400, 409, 422, 507} for response in invalid_responses),
                "idempotency_baseline_event_accepted": idempotency_original_response.status_code == 200
                and idempotency_original_response.payload.get("success") is True,
                "idempotency_conflict_rejected": idempotency_conflict_response.status_code in {400, 409},
                "persistence_error_returns_failure": persistence_response.status_code in {500, 503, 507}
                and persistence_response.payload.get("success") is not True,
                "oversized_illegal_payload_is_safe": oversized_response.status_code in {400, 413, 422},
                "business_event_list_remains_clean": all(
                    self._find_event(events, scenario.submission.source_system, scenario.submission.event_id) is None
                    for scenario in illegal_scenarios
                )
                and self._find_event(
                    events,
                    oversized_illegal_submission.source_system,
                    oversized_illegal_submission.event_id,
                )
                is None
                and self._find_event(
                    events,
                    idempotency_conflict_submission.source_system,
                    idempotency_conflict_submission.event_id,
                )
                is not None
                and self._count_events(
                    events,
                    idempotency_conflict_submission.source_system,
                    idempotency_conflict_submission.event_id,
                )
                == 1
                and self._find_event(
                    events,
                    persistence_error_submission.source_system,
                    persistence_error_submission.event_id,
                )
                is None,
                "failure_records_exist_for_every_failed_branch": all(
                    self._find_failure_record(failures, event_id) is not None
                    for event_id in expected_failed_event_ids
                ),
                "all_failure_summaries_are_bounded": all(
                    len(str(record.get("requestSummary", ""))) <= _MAX_FAILURE_SUMMARY_CHARS
                    for record in failures
                )
                and bool(failures),
            },
            responses=[
                *invalid_responses,
                idempotency_original_response,
                idempotency_conflict_response,
                persistence_response,
                oversized_response,
                event_list,
                failure_records,
            ],
        )

    def web_lists_filters_and_opens_event_detail(
        self,
        accepted_events: tuple[SecurityEventSubmission, ...],
    ) -> SecurityEventObservation:
        submit_responses = [self._submit_event(event) for event in accepted_events]
        list_page = self._web_page("/security-events")
        first_event = accepted_events[0]
        source_filter_list = self._list_events(query=f"?sourceSystem={first_event.source_system}")
        type_filter_list = self._list_events(query=f"?eventTypeId={first_event.event_type_id}")
        severity_filter_list = self._list_events(query=f"?severity={first_event.severity}")
        time_filter_list = self._list_events(
            query="?occurredFrom=2026-06-12T03:00:00Z&occurredTo=2026-06-12T03:30:00Z",
        )
        detail_page = self._web_page(f"/security-events/{first_event.source_system}/{first_event.event_id}")
        detail_api = self._event_detail(first_event.source_system, first_event.event_id)
        source_filtered_events = source_filter_list.payload.get("events", []) if source_filter_list.ok else []
        type_filtered_events = type_filter_list.payload.get("events", []) if type_filter_list.ok else []
        severity_filtered_events = severity_filter_list.payload.get("events", []) if severity_filter_list.ok else []
        time_filtered_events = time_filter_list.payload.get("events", []) if time_filter_list.ok else []
        all_filtered_events = (
            source_filtered_events
            + type_filtered_events
            + severity_filtered_events
            + time_filtered_events
        )
        matching_list_event = self._find_event(source_filtered_events, first_event.source_system, first_event.event_id)
        structured_payload = detail_api.payload.get("structuredPayload", {})
        undefined_payload = detail_api.payload.get("undefinedPayloadFields", {})
        raw_payload = detail_api.payload.get("rawPayload", {})

        return self._observation(
            category="Security_Event_Inbox_Web_Gap",
            control_point=(
                "Seed multiple accepted events, open the Web inbox, apply source/type/"
                "severity/time filters, and navigate to a stable detail URL."
            ),
            observation_point=(
                "Web/API inbox defaults to receivedAt descending, exposes core fields, "
                "event type display name, configured list payload fields, source/type/"
                "severity/time filters, and stable detail with base facts, structured "
                "payload, undefined fields, and bounded raw payload."
            ),
            checks={
                "seed_events_accepted": all(response.status_code == 200 for response in submit_responses),
                "web_inbox_route_exists": list_page.status_code == 200
                and "security event" in list_page.text.lower(),
                "source_filter_returns_only_matching_source": bool(source_filtered_events)
                and all(event.get("sourceSystem") == first_event.source_system for event in source_filtered_events),
                "type_filter_returns_only_matching_type": bool(type_filtered_events)
                and all(event.get("eventTypeId") == first_event.event_type_id for event in type_filtered_events),
                "severity_filter_returns_only_matching_severity": bool(severity_filtered_events)
                and all(event.get("severity") == first_event.severity for event in severity_filtered_events),
                "time_filter_returns_only_matching_window": bool(time_filtered_events)
                and all(
                    "2026-06-12T03:" in str(event.get("occurredAt", ""))
                    for event in time_filtered_events
                ),
                "list_defaults_received_at_descending": self._received_at_descending(source_filtered_events),
                "core_columns_are_present": self._has_core_list_fields(source_filtered_events),
                "event_type_display_name_is_visible": bool(matching_list_event)
                and bool(matching_list_event.get("eventTypeDisplayName")),
                "configured_list_payload_field_is_visible": bool(matching_list_event)
                and "assetId" in matching_list_event,
                "stable_detail_url_exists": detail_page.status_code == 200,
                "detail_base_facts_are_visible": detail_api.ok
                and detail_api.payload.get("sourceSystem") == first_event.source_system
                and detail_api.payload.get("eventId") == first_event.event_id
                and detail_api.payload.get("summary") == first_event.summary,
                "detail_structured_payload_is_visible": "assetId" in structured_payload
                and "detectionName" in structured_payload,
                "detail_undefined_fields_are_visible": "collectorBuildFingerprint" in undefined_payload,
                "detail_raw_payload_is_visible_and_bounded": "collectorBuildFingerprint" in raw_payload
                and len(str(raw_payload)) <= _MAX_FAILURE_SUMMARY_CHARS,
            },
            responses=[
                *submit_responses,
                list_page,
                source_filter_list,
                type_filter_list,
                severity_filter_list,
                time_filter_list,
                detail_page,
                detail_api,
            ],
        )

    def _submit_event(
        self,
        submission: SecurityEventSubmission,
        *,
        headers: dict[str, str] | None = None,
    ) -> "_HarnessResponse":
        return self._request_json(
            "POST",
            "/security-center/v1/events",
            json_body=submission.request_body(),
            headers=headers,
        )

    def _list_events(self, query: str = "") -> "_HarnessResponse":
        return self._request_json("GET", f"/security-center/v1/operator/events{query}")

    def _event_detail(self, source_system: str, event_id: str) -> "_HarnessResponse":
        return self._request_json("GET", f"/security-center/v1/operator/events/{source_system}/{event_id}")

    def _failure_records(self) -> "_HarnessResponse":
        return self._request_json("GET", "/security-center/v1/operator/event-reception-failures")

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> "_HarnessResponse":
        if not self.api_base_url:
            return _HarnessResponse(status_code=0, payload={}, text="Security Center API URL is unavailable.")
        try:
            with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
                response = client.request(
                    method,
                    f"{self.api_base_url}{path}",
                    json=json_body,
                    headers=headers,
                )
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            return _HarnessResponse(
                status_code=response.status_code,
                payload=payload,
                text=response.text,
                path=path,
            )
        except httpx.HTTPError as exc:
            return _HarnessResponse(status_code=0, payload={}, text=str(exc), path=path)

    def _web_page(self, path: str) -> "_HarnessResponse":
        if not self.web_base_url:
            return _HarnessResponse(status_code=0, payload={}, text="Security Center Web URL is unavailable.")
        try:
            with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS, follow_redirects=True) as client:
                response = client.get(f"{self.web_base_url}{path}")
            return _HarnessResponse(status_code=response.status_code, payload={}, text=response.text, path=path)
        except httpx.HTTPError as exc:
            return _HarnessResponse(status_code=0, payload={}, text=str(exc), path=path)

    def _observation(
        self,
        *,
        category: str,
        control_point: str,
        observation_point: str,
        checks: dict[str, bool],
        responses: list["_HarnessResponse"],
    ) -> SecurityEventObservation:
        failure_reasons = [name for name, ready in checks.items() if not ready]
        for response in responses:
            if response.status_code == 404:
                failure_reasons.append(f"Security_Event_Ingestion_API_Missing:{response.path}")
            elif response.status_code == 0:
                failure_reasons.append(f"Security_Event_Ingestion_Endpoint_Unreachable:{response.path}")
        diagnostic = "\n".join(
            f"{response.path or '<unknown>'} status={response.status_code} body={response.text[:500]}"
            for response in responses
            if not response.ok
        )
        return SecurityEventObservation(
            category=category,
            control_point=control_point,
            observation_point=observation_point,
            checks=checks,
            failure_reasons=tuple(dict.fromkeys(failure_reasons)),
            diagnostic=diagnostic,
        )

    @staticmethod
    def _has_reason(response: "_HarnessResponse", expected_reason: str) -> bool:
        return expected_reason in json.dumps(response.payload, ensure_ascii=False) or expected_reason in response.text

    @staticmethod
    def _find_event(events: Any, source_system: str, event_id: str) -> dict[str, Any] | None:
        if not isinstance(events, list):
            return None
        for event in events:
            if event.get("sourceSystem") == source_system and event.get("eventId") == event_id:
                return event
        return None

    @classmethod
    def _count_events(cls, events: Any, source_system: str, event_id: str) -> int:
        if not isinstance(events, list):
            return 0
        return sum(1 for event in events if cls._find_event([event], source_system, event_id) is not None)

    @staticmethod
    def _find_failure_record(records: Any, event_id: str) -> dict[str, Any] | None:
        if not isinstance(records, list):
            return None
        for record in records:
            if record.get("eventId") == event_id or event_id in str(record.get("requestSummary", "")):
                return record
        return None

    @staticmethod
    def _received_at_descending(events: Any) -> bool:
        if not isinstance(events, list) or len(events) < 2:
            return bool(events)
        received_values = [str(event.get("receivedAt", "")) for event in events]
        return received_values == sorted(received_values, reverse=True)

    @staticmethod
    def _has_core_list_fields(events: Any) -> bool:
        if not isinstance(events, list) or not events:
            return False
        required = {"receivedAt", "occurredAt", "sourceSystem", "eventTypeId", "severity", "summary", "eventId"}
        return required.issubset(events[0].keys())


@dataclass(frozen=True)
class _HarnessResponse:
    status_code: int
    payload: dict[str, Any]
    text: str = ""
    path: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300
