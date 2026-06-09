from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx

if TYPE_CHECKING:
    from tests.integration.conftest import AppServer

_HTTP_TIMEOUT = 45.0
_STREAM_READ_TIMEOUT = 5.0
_RUNTIME_SETTLE_SECONDS = 5.0
_RUNTIME_POLL_INTERVAL_SECONDS = 0.25
_RUNTIME_RESTART_READY_SECONDS = 70.0


def _drain_process_output(stream: Any, buffer: list[str]) -> None:
    try:
        for line in iter(stream.readline, ""):
            buffer.append(line)
            try:
                print(f"[app server] {line}", end="", flush=True)
            except (OSError, ValueError):
                pass
    finally:
        stream.close()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _canonical_hash(label: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json({"label": label, "payload": payload}).encode("utf-8"),
    ).hexdigest()


@dataclass(frozen=True)
class EmployeeIdentity:
    employee_id: str
    channel_name: str
    authenticated_session_id: str


@dataclass(frozen=True)
class HighRiskDelegationRequest:
    authenticated_employee: EmployeeIdentity
    delegated_agent_name: str
    third_party_plugin_name: str
    high_risk_tool_name: str
    user_confirmation_phrase: str

    def digest(self) -> str:
        joined = "|".join(
            (
                self.authenticated_employee.employee_id,
                self.authenticated_employee.channel_name,
                self.authenticated_employee.authenticated_session_id,
                self.delegated_agent_name,
                self.third_party_plugin_name,
                self.high_risk_tool_name,
                self.user_confirmation_phrase,
            ),
        )
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()


@dataclass
class RuntimeContextInspection:
    expected_user_id: str
    observed_user_id: str | None = None
    implicit_contextvars_ready: bool = False
    tool_boundary_probe_ready: bool = False
    explicit_parameter_threading_guarded: bool = False
    failure_reasons: tuple[str, ...] = ()

    def is_trusted(self) -> bool:
        return all(
            (
                self.observed_user_id == self.expected_user_id,
                self.implicit_contextvars_ready,
                self.tool_boundary_probe_ready,
                self.explicit_parameter_threading_guarded,
                not self.failure_reasons,
            ),
        )


@dataclass(frozen=True)
class EvidenceChainObservation:
    observed_actor_chain: tuple[str, ...]
    continuous_chain_ready: bool
    confirmation_artifact_digest: str | None
    security_center_query_ready: bool
    failure_reasons: tuple[str, ...]

    def is_contract_ready(self) -> bool:
        return all(
            (
                len(self.observed_actor_chain) == 4,
                self.continuous_chain_ready,
                self.confirmation_artifact_digest is not None,
                self.security_center_query_ready,
                not self.failure_reasons,
            ),
        )


@dataclass(frozen=True)
class AuditLedgerRecordObservation:
    ledger_path: str
    event_type: str | None
    payload_hash: str | None
    has_prior_hash: bool
    physical_record_present: bool
    failure_reasons: tuple[str, ...]

    def matches_confirmation_artifact(self, expected_digest: str) -> bool:
        return all(
            (
                self.physical_record_present,
                self.event_type == "USER_CONFIRMATION",
                self.payload_hash == expected_digest,
                self.has_prior_hash,
                not self.failure_reasons,
            ),
        )


@dataclass(frozen=True)
class HashChainIntegrityObservation:
    hash_fields_present: bool
    verifier_ready: bool
    continuity_anchor_ready: bool
    failure_reasons: tuple[str, ...]

    def is_intact(self) -> bool:
        return all(
            (
                self.hash_fields_present,
                self.verifier_ready,
                self.continuity_anchor_ready,
                not self.failure_reasons,
            ),
        )


@dataclass(frozen=True)
class PreExecutionEvidenceObservation:
    confirmation_gate_ready: bool
    synchronous_evidence_write_ready: bool
    ordering_ready: bool
    failure_reasons: tuple[str, ...]

    def is_pre_execution(self) -> bool:
        return all(
            (
                self.confirmation_gate_ready,
                self.synchronous_evidence_write_ready,
                self.ordering_ready,
                not self.failure_reasons,
            ),
        )


@dataclass(frozen=True)
class AuditIntegrityTamperRequest:
    authenticated_employee: EmployeeIdentity
    baseline_high_risk_action_labels: tuple[str, ...]
    tampered_record_position_from_start: int
    sensitive_tool_name: str
    tampered_artifact_label: str
    reconnect_action_label: str
    security_center_backend_api_name: str
    security_center_operator_web_name: str
    hash_break_curve_chart_name: str


@dataclass(frozen=True)
class AuditIntegrityLockdownObservation:
    tampered_artifact_path: str
    baseline_cloud_anchor_ready: bool
    historical_multi_record_baseline_ready: bool
    tampered_record_is_second_non_tail: bool
    historical_record_tamper_detected: bool
    continuity_anomaly_ready: bool
    checkpoint_loss_treated_as_tamper: bool
    local_lock_mode_ready: bool
    sensitive_tool_blocked: bool
    external_anchor_divergence_ready: bool
    rebuilt_chain_recovery_gate_ready: bool
    backend_api_projection_ready: bool
    operator_web_projection_ready: bool
    hash_break_curve_chart_ready: bool
    hash_break_fork_point_ready: bool
    cloud_recovery_projection_ready: bool
    recovery_handshake_ready: bool
    security_center_clear_blocked: bool
    failure_reasons: tuple[str, ...]

    def enforces_lockdown(self) -> bool:
        return all(
            (
                self.baseline_cloud_anchor_ready,
                self.historical_multi_record_baseline_ready,
                self.tampered_record_is_second_non_tail,
                self.historical_record_tamper_detected,
                self.continuity_anomaly_ready,
                self.local_lock_mode_ready,
                self.sensitive_tool_blocked,
                self.external_anchor_divergence_ready,
                self.rebuilt_chain_recovery_gate_ready,
                self.backend_api_projection_ready,
                self.operator_web_projection_ready,
                self.hash_break_curve_chart_ready,
                self.hash_break_fork_point_ready,
                self.cloud_recovery_projection_ready,
                self.recovery_handshake_ready,
                self.security_center_clear_blocked,
                not self.failure_reasons,
            ),
        )


@dataclass(frozen=True)
class LeaseExpiryRecoveryRequest:
    authenticated_employee: EmployeeIdentity
    lease_monitor_name: str
    security_center_backend_api_name: str
    security_center_operator_web_name: str
    missing_gap_verification_label: str
    restored_model_access_label: str


@dataclass(frozen=True)
class LeaseExpiryRecoveryObservation:
    baseline_client_registration_ready: bool
    heartbeat_projection_ready: bool
    pre_recovery_lease_monitor_projection_ready: bool
    pre_recovery_backend_api_projection_ready: bool
    pre_recovery_operator_web_projection_ready: bool
    pre_recovery_reconnect_denied_ready: bool
    recovery_control_point_ready: bool
    post_recovery_backend_api_projection_ready: bool
    post_recovery_operator_web_projection_ready: bool
    post_recovery_model_access_ready: bool
    pre_recovery_console_status: int | None
    post_recovery_console_status: int | None
    pre_recovery_trust_state: str | None
    post_recovery_trust_state: str | None
    failure_reasons: tuple[str, ...]

    def blocks_rejoin_until_gap_sync(self) -> bool:
        return all(
            (
                self.baseline_client_registration_ready,
                self.heartbeat_projection_ready,
                self.pre_recovery_lease_monitor_projection_ready,
                self.pre_recovery_backend_api_projection_ready,
                self.pre_recovery_operator_web_projection_ready,
                self.pre_recovery_reconnect_denied_ready,
                self.recovery_control_point_ready,
                self.post_recovery_backend_api_projection_ready,
                self.post_recovery_operator_web_projection_ready,
                self.post_recovery_model_access_ready,
                not self.failure_reasons,
            ),
        )


@dataclass(frozen=True)
class NormalOfflineReconnectRequest:
    authenticated_employee: EmployeeIdentity
    normal_offline_action_label: str
    restored_model_access_label: str
    security_center_backend_api_name: str
    security_center_operator_web_name: str


@dataclass(frozen=True)
class NormalOfflineReconnectObservation:
    baseline_client_registration_ready: bool
    trusted_audit_head_ready: bool
    normal_offline_control_point_ready: bool
    runtime_restarted_before_lease_expiry: bool
    backend_clear_projection_ready: bool
    operator_web_clear_projection_ready: bool
    ordinary_model_access_ready: bool
    no_gap_validation_required: bool
    model_access_status: int | None
    baseline_client_id: str | None
    baseline_trust_state: str | None
    post_reconnect_trust_state: str | None
    post_reconnect_gap_status: str | None
    post_reconnect_recovery_gate_status: str | None
    post_reconnect_recovery_required: bool | None
    failure_reasons: tuple[str, ...]

    def reconnects_clear_without_gap_recovery(self) -> bool:
        return all(
            (
                self.baseline_client_registration_ready,
                self.trusted_audit_head_ready,
                self.normal_offline_control_point_ready,
                self.runtime_restarted_before_lease_expiry,
                self.backend_clear_projection_ready,
                self.operator_web_clear_projection_ready,
                self.ordinary_model_access_ready,
                self.no_gap_validation_required,
                not self.failure_reasons,
            ),
        )


@dataclass(frozen=True)
class PromptInjectionAttempt:
    authenticated_employee: EmployeeIdentity
    deceptive_instruction_text: str
    targeted_high_risk_tool_name: str
    bypass_narrative_label: str
    security_center_backend_api_name: str
    security_center_operator_web_name: str
    nonce_voucher_label: str


@dataclass(frozen=True)
class PromptInjectionGuardObservation:
    tool_boundary_guard_ready: bool
    missing_trusted_context_rejected: bool
    durable_rejected_event_ready: bool
    backend_api_rejection_ready: bool
    operator_web_rejection_ready: bool
    nonce_voucher_ready: bool
    realtime_push_channel_ready: bool
    realtime_red_alert_ready: bool
    observed_alert_latency_ms: int | None
    security_center_mirror_ready: bool
    security_rejection_nonce: str | None
    security_rejection_nonce_trace_bound: bool
    failure_reasons: tuple[str, ...]

    def denies_execution(self) -> bool:
        return all(
            (
                self.tool_boundary_guard_ready,
                self.missing_trusted_context_rejected,
                self.durable_rejected_event_ready,
                self.backend_api_rejection_ready,
                self.operator_web_rejection_ready,
                self.nonce_voucher_ready,
                self.realtime_push_channel_ready,
                self.realtime_red_alert_ready,
                self.security_center_mirror_ready,
                self.security_rejection_nonce is not None,
                self.security_rejection_nonce_trace_bound,
                not self.failure_reasons,
            ),
        )


class SecurityAuditHarness:
    def __init__(self, app_server: AppServer) -> None:
        self._app_server = app_server
        self._trace_dir = app_server.working_dir / "inbox_traces"
        self._active_context_probe: RuntimeContextInspection | None = None
        self._latest_trace_paths: tuple[Path, ...] = ()
        self._latest_approval_payload: dict[str, Any] = {}
        self._latest_trace_query_ready = False
        self._latest_console_status: int | None = None
        self._latest_console_error: str | None = None
        self._latest_console_response_headers: dict[str, str] = {}
        self._latest_console_response_body = ""

    @classmethod
    def for_app_server(cls, app_server: AppServer) -> "SecurityAuditHarness":
        return cls(app_server)

    @contextmanager
    def expect_context_propagation(
        self,
        *,
        expected_user_id: str,
    ):
        inspection = RuntimeContextInspection(expected_user_id=expected_user_id)
        self._active_context_probe = inspection
        try:
            yield inspection
        finally:
            self._active_context_probe = None

    def execute_high_risk_delegation_with_confirmation(
        self,
        request: HighRiskDelegationRequest,
    ) -> EvidenceChainObservation:
        if self._app_server.startup_error is not None:
            self._latest_console_status = None
            self._latest_console_error = self._app_server.startup_error
            self._update_context_probe(
                expected_user_id=request.authenticated_employee.employee_id,
                latest_trace_payload={},
                approval_records=[],
            )
            return EvidenceChainObservation(
                observed_actor_chain=(),
                continuous_chain_ready=False,
                confirmation_artifact_digest=None,
                security_center_query_ready=False,
                failure_reasons=(
                    "Real_Runtime_Bootstrap_Blocking_Dependency: the real app "
                    "subprocess could not finish startup in the shared test "
                    "environment, so sec-e2e-024 could not reach its live "
                    "delegation flow.",
                ),
            )
        before_trace_names = {path.name for path in self._trace_files()}
        version_response = self._app_server.api_request(
            "GET",
            "/api/version",
            timeout=_HTTP_TIMEOUT,
        )
        self._trigger_live_console_attempt(request)
        self._collect_runtime_artifacts(
            session_id=request.authenticated_employee.authenticated_session_id,
            before_trace_names=before_trace_names,
        )

        approval_records = self._latest_pending_approvals()
        latest_trace_payload = self._load_latest_trace_payload()
        observed_actor_chain = self._extract_actor_chain(
            request=request,
            approval_records=approval_records,
            trace_payload=latest_trace_payload,
        )
        confirmation_artifact_digest = self._find_first_scalar(
            latest_trace_payload,
            keys=("payload_hash", "confirmation_digest", "confirmation_signature"),
        ) or self._find_first_scalar(
            approval_records,
            keys=("payload_hash", "confirmation_digest", "confirmation_signature"),
        )
        continuous_chain_ready = len(observed_actor_chain) == 4 and all(
            (
                confirmation_artifact_digest is not None,
                self._latest_trace_query_ready,
            ),
        )

        self._update_context_probe(
            expected_user_id=request.authenticated_employee.employee_id,
            latest_trace_payload=latest_trace_payload,
            approval_records=approval_records,
        )

        failure_reasons: list[str] = []
        if version_response.status_code != 200:
            failure_reasons.append(
                "Real_Runtime_Unavailable: the live app subprocess did not stay "
                "healthy enough to answer GET /api/version for sec-e2e-024."
            )
        if self._latest_console_status != 200:
            failure_reasons.append(
                "Runtime_Delegation_Attempt_Failed: the live app did not accept "
                "the delegated high-risk console request in the isolated runtime."
            )
        if len(observed_actor_chain) != 4:
            failure_reasons.append(
                "Actor_Lineage_Incomplete: the live app did not emit structured "
                "runtime evidence for every required business hop from employee "
                "to agent to plugin to tool."
            )
        if confirmation_artifact_digest is None:
            failure_reasons.append(
                "Confirmation_Artifact_Missing: the live app did not persist a "
                "durable confirmation digest in approval or trace artifacts under "
                "the isolated working directory."
            )
        if not self._latest_trace_query_ready:
            failure_reasons.append(
                "Security_Center_Query_Missing: the live app did not expose a "
                "queryable runtime trace for the attempted high-risk session."
            )
        if not continuous_chain_ready:
            failure_reasons.append(
                "Evidence_Projection_Missing: the live app did not materialize "
                "one queryable runtime record that reconstructs employee -> "
                "agent -> plugin -> tool for the attempted session."
            )

        return EvidenceChainObservation(
            observed_actor_chain=observed_actor_chain,
            continuous_chain_ready=continuous_chain_ready,
            confirmation_artifact_digest=confirmation_artifact_digest,
            security_center_query_ready=self._latest_trace_query_ready,
            failure_reasons=tuple(failure_reasons),
        )

    def get_last_audit_record_from_disk(self) -> AuditLedgerRecordObservation:
        latest_trace_path = self._latest_trace_path()
        latest_trace_payload = self._load_latest_trace_payload()
        event_type = self._find_first_scalar(
            latest_trace_payload,
            keys=("event_type", "type"),
        )
        payload_hash = self._find_first_scalar(
            latest_trace_payload,
            keys=("payload_hash", "confirmation_digest", "confirmation_signature"),
        )
        has_prior_hash = self._contains_all_keys(
            latest_trace_payload,
            required_keys=("prior_hash",),
        )
        physical_record_present = latest_trace_path is not None

        failure_reasons: list[str] = []
        if not physical_record_present:
            failure_reasons.append(
                "Physical_Audit_Record_Missing: the isolated runtime did not "
                "write any disk artifact under inbox_traces for sec-e2e-024."
            )
        if event_type != "USER_CONFIRMATION":
            failure_reasons.append(
                "Confirmation_Record_Type_Missing: the latest live runtime "
                "artifact does not expose a USER_CONFIRMATION record type for "
                "direct inspection."
            )
        if payload_hash is None:
            failure_reasons.append(
                "Confirmation_Payload_Hash_Missing: the latest live runtime "
                "artifact does not persist the confirmation artifact digest."
            )
        if not has_prior_hash:
            failure_reasons.append(
                "Prior_Hash_Link_Missing: the latest live runtime artifact does "
                "not expose a prior-hash anchor for chain verification."
            )

        return AuditLedgerRecordObservation(
            ledger_path=str(latest_trace_path or self._trace_dir),
            event_type=event_type,
            payload_hash=payload_hash,
            has_prior_hash=has_prior_hash,
            physical_record_present=physical_record_present,
            failure_reasons=tuple(failure_reasons),
        )

    def verify_local_hash_chain_integrity(self) -> HashChainIntegrityObservation:
        latest_trace_payload = self._load_latest_trace_payload()
        hash_fields_present = self._contains_all_keys(
            latest_trace_payload,
            required_keys=("prior_hash", "current_hash"),
        )
        verifier_ready = self._contains_any_key(
            latest_trace_payload,
            candidate_keys=("hash_chain_valid", "verified_at", "hash_chain_status"),
        )
        continuity_anchor_ready = (
            self._app_server.working_dir / "audit_chain_checkpoint.json"
        ).exists() or self._contains_any_key(
            latest_trace_payload,
            candidate_keys=("checkpoint_hash", "anchor_hash", "continuity_anchor"),
        )

        failure_reasons: list[str] = []
        if not hash_fields_present:
            failure_reasons.append(
                "Hash_Fields_Missing: the live runtime artifact does not yet "
                "expose both prior_hash and current_hash for integrity verification."
            )
        if not verifier_ready:
            failure_reasons.append(
                "Hash_Chain_Verifier_Missing: the isolated runtime does not yet "
                "emit any verifier result for the local audit chain."
            )
        if not continuity_anchor_ready:
            failure_reasons.append(
                "Continuity_Anchor_Missing: the isolated runtime does not yet "
                "emit a checkpoint or continuity anchor artifact for sec-e2e-024."
            )

        return HashChainIntegrityObservation(
            hash_fields_present=hash_fields_present,
            verifier_ready=verifier_ready,
            continuity_anchor_ready=continuity_anchor_ready,
            failure_reasons=tuple(failure_reasons),
        )

    def verify_confirmation_precedes_high_risk_tool_effect(
        self,
        request: HighRiskDelegationRequest,
    ) -> PreExecutionEvidenceObservation:
        approval_records = self._latest_pending_approvals()
        latest_trace_payload = self._load_latest_trace_payload()
        confirmation_gate_ready = any(
            record.get("session_id")
            == request.authenticated_employee.authenticated_session_id
            for record in approval_records
            if isinstance(record, dict)
        )
        synchronous_evidence_write_ready = self._find_first_scalar(
            latest_trace_payload,
            keys=("payload_hash", "confirmation_digest"),
        ) is not None

        confirmation_at = self._find_first_scalar(
            latest_trace_payload,
            keys=("confirmed_at", "approved_at", "confirmation_at"),
        )
        tool_effect_at = self._find_first_scalar(
            latest_trace_payload,
            keys=("tool_effect_at", "executed_at", "released_at"),
        )
        ordering_ready = (
            isinstance(confirmation_at, (int, float))
            and isinstance(tool_effect_at, (int, float))
            and confirmation_at <= tool_effect_at
        )

        failure_reasons: list[str] = []
        if not confirmation_gate_ready:
            failure_reasons.append(
                "Human_Approval_Gate_Missing: the live app did not emit a "
                "pending approval record for the attempted high-risk session."
            )
        if not synchronous_evidence_write_ready:
            failure_reasons.append(
                "Pre_Execution_Evidence_Write_Missing: no durable confirmation "
                "record was observed in the live working directory during the "
                "attempted high-risk flow."
            )
        if not ordering_ready:
            failure_reasons.append(
                "Pre_Execution_Order_Assertion_Missing: the live runtime "
                "artifacts do not prove the atomic order 'store evidence, then "
                "release the high-risk tool'."
            )

        return PreExecutionEvidenceObservation(
            confirmation_gate_ready=confirmation_gate_ready,
            synchronous_evidence_write_ready=synchronous_evidence_write_ready,
            ordering_ready=ordering_ready,
            failure_reasons=tuple(failure_reasons),
        )

    def render_non_repudiation_failure_report(
        self,
        *,
        context_propagation_at_tool_boundary: RuntimeContextInspection,
        observed_evidence_chain: EvidenceChainObservation,
        last_audit_record: AuditLedgerRecordObservation,
        local_hash_chain_integrity: HashChainIntegrityObservation,
        pre_execution_evidence_order: PreExecutionEvidenceObservation,
        expected_confirmation_digest: str,
    ) -> str:
        failures = [
            *context_propagation_at_tool_boundary.failure_reasons,
            *observed_evidence_chain.failure_reasons,
            *last_audit_record.failure_reasons,
            *local_hash_chain_integrity.failure_reasons,
            *pre_execution_evidence_order.failure_reasons,
        ]
        lines = ['category="Non_Repudiation_Gap"']
        for failure in dict.fromkeys(failures):
            lines.append(f"- {failure}")
        lines.append(
            "observed_actor_chain="
            + " -> ".join(observed_evidence_chain.observed_actor_chain),
        )
        lines.append(
            "observed_tool_boundary_identity="
            + (
                context_propagation_at_tool_boundary.observed_user_id
                or "<missing>"
            )
        )
        lines.append("expected_confirmation_digest=" + expected_confirmation_digest)
        lines.append(
            "persisted_confirmation_digest="
            + (last_audit_record.payload_hash or "<missing>"),
        )
        lines.append("physical_ledger_path=" + last_audit_record.ledger_path)
        lines.append("runtime_base_url=" + self._app_server.base_url)
        lines.append("runtime_working_dir=" + str(self._app_server.working_dir))
        lines.append(
            "runtime_console_status="
            + (
                str(self._latest_console_status)
                if self._latest_console_status is not None
                else "<missing>"
            ),
        )
        if self._latest_console_error:
            lines.append("runtime_console_error=" + self._latest_console_error)
        return "\n".join(lines)

    def verify_tamper_evidence_forces_lockdown(
        self,
        request: AuditIntegrityTamperRequest,
    ) -> AuditIntegrityLockdownObservation:
        if self._app_server.startup_error is not None:
            return AuditIntegrityLockdownObservation(
                tampered_artifact_path=str(self._app_server.working_dir),
                baseline_cloud_anchor_ready=False,
                historical_multi_record_baseline_ready=False,
                tampered_record_is_second_non_tail=False,
                historical_record_tamper_detected=False,
                continuity_anomaly_ready=False,
                checkpoint_loss_treated_as_tamper=False,
                local_lock_mode_ready=False,
                sensitive_tool_blocked=False,
                external_anchor_divergence_ready=False,
                rebuilt_chain_recovery_gate_ready=False,
                backend_api_projection_ready=False,
                operator_web_projection_ready=False,
                hash_break_curve_chart_ready=False,
                hash_break_fork_point_ready=False,
                cloud_recovery_projection_ready=False,
                recovery_handshake_ready=False,
                security_center_clear_blocked=False,
                failure_reasons=(
                    "Real_Runtime_Bootstrap_Blocking_Dependency: the real app "
                    "subprocess could not finish startup, so sec-e2e-025 could "
                    "not drive a live tamper-and-resume flow.",
                ),
            )

        for action_index, high_risk_action_label in enumerate(
            request.baseline_high_risk_action_labels,
            start=1,
        ):
            baseline_request = HighRiskDelegationRequest(
                authenticated_employee=request.authenticated_employee,
                delegated_agent_name="security_audit_agent",
                third_party_plugin_name=request.security_center_backend_api_name,
                high_risk_tool_name=request.sensitive_tool_name,
                user_confirmation_phrase=(
                    "Approve audit integrity baseline capture "
                    f"{action_index}: {high_risk_action_label}"
                ),
            )
            before_trace_names = {path.name for path in self._trace_files()}
            self._trigger_live_console_attempt(baseline_request)
            self._collect_runtime_artifacts(
                session_id=request.authenticated_employee.authenticated_session_id,
                before_trace_names=before_trace_names,
            )

        baseline_trace_paths = self._trace_files()
        historical_multi_record_baseline_ready = (
            len(baseline_trace_paths) >= len(request.baseline_high_risk_action_labels)
            and len(baseline_trace_paths) >= 3
        )
        baseline_overview = self._read_security_center_api_json(
            "/security-center/v1/operator/overview",
        )
        baseline_client = self._find_client_state(
            baseline_overview,
            client_id=request.authenticated_employee.authenticated_session_id,
        )
        baseline_trusted_sequence = 0
        if isinstance(baseline_client, dict):
            try:
                baseline_trusted_sequence = int(
                    baseline_client.get("last_trusted_sequence") or 0,
                )
            except (TypeError, ValueError):
                baseline_trusted_sequence = 0
        baseline_cloud_anchor_ready = all(
            (
                isinstance(baseline_client, dict),
                baseline_trusted_sequence > 0,
                not str(
                    baseline_client.get("last_trusted_anchor_event_id") or "",
                ).startswith("shadow-anchor::"),
            ),
        )

        tampered_artifact_path = self._tamper_committed_historical_audit_record(
            artifact_label=request.tampered_artifact_label,
            baseline_trace_paths=baseline_trace_paths,
            record_position_from_start=request.tampered_record_position_from_start,
        )
        tampered_trace_payload = self._load_json_file(Path(tampered_artifact_path))
        tampered_local_hash = self._find_first_scalar(
            tampered_trace_payload,
            keys=("current_hash", "continuity_anchor"),
        ) or "tampered-current-hash"
        divergence_probe = self._post_security_center_api_json(
            "/security-center/v1/recovery/handshake",
            json={
                "client_id": request.authenticated_employee.authenticated_session_id,
                "trace_id": f"external-anchor-probe::{request.authenticated_employee.authenticated_session_id}",
                "local_hash": tampered_local_hash,
                "checkpoint_hash": tampered_local_hash,
                "requested_at_ns": time.time_ns(),
            },
        )
        shadow_hash = self._find_first_scalar(
            divergence_probe,
            keys=("shadow_hash",),
        )
        rebuilt_chain_probe = self._post_security_center_api_json(
            "/security-center/v1/recovery/handshake",
            json={
                "client_id": request.authenticated_employee.authenticated_session_id,
                "trace_id": f"rebuilt-chain-probe::{request.authenticated_employee.authenticated_session_id}",
                "local_hash": shadow_hash or tampered_local_hash,
                "checkpoint_hash": shadow_hash or tampered_local_hash,
                "requested_at_ns": time.time_ns(),
            },
        ) if shadow_hash else {}
        resume_prompt = (
            f"Resume {request.reconnect_action_label} with high-risk tool "
            f"{request.sensitive_tool_name} after reconnect."
        )
        after_tamper_names = {path.name for path in self._trace_files()}
        self._submit_console_prompt(
            user_id=request.authenticated_employee.employee_id,
            session_id=request.authenticated_employee.authenticated_session_id,
            prompt=resume_prompt,
        )
        self._collect_runtime_artifacts(
            session_id=request.authenticated_employee.authenticated_session_id,
            before_trace_names=after_tamper_names,
        )

        latest_trace_payload = self._load_latest_trace_payload()
        security_center_timeline = self._read_security_center_api_json(
            f"/security-center/v1/operator/timelines/{quote(request.authenticated_employee.authenticated_session_id, safe='')}",
        )
        security_center_overview = self._read_security_center_api_json(
            "/security-center/v1/operator/overview",
        )
        security_center_web_html = self._read_security_center_web_text("/")
        security_center_web_app = self._read_security_center_web_text("/app.js")
        checkpoint_path = self._app_server.working_dir / "audit_chain_checkpoint.json"
        checkpoint_missing_detected = not checkpoint_path.exists()
        tampered_record_is_second_non_tail = (
            request.tampered_record_position_from_start == 2
            and len(baseline_trace_paths) > request.tampered_record_position_from_start
            and Path(tampered_artifact_path) == baseline_trace_paths[1]
        )
        trust_state = self._find_first_scalar(
            latest_trace_payload,
            keys=("lock_mode", "security_lock_mode", "trust_state"),
        )
        continuity_anomaly_ready = self._contains_any_key(
            latest_trace_payload,
            candidate_keys=(
                "anomaly_category",
                "continuity_status",
                "integrity_alert",
                "tamper_detected",
                "checkpoint_missing",
            ),
        )
        historical_record_tamper_detected = self._contains_any_key(
            latest_trace_payload,
            candidate_keys=(
                "historical_record_tamper_detected",
                "ledger_record_tamper_detected",
                "hash_chain_break_detected",
                "non_tail_record_tamper_detected",
            ),
        ) or (
            continuity_anomaly_ready
            and self._contains_any_key(
                latest_trace_payload,
                candidate_keys=(
                    "tampered_record_position",
                    "tampered_event_sequence",
                    "fork_point",
                    "fork_event_id",
                ),
            )
        )
        checkpoint_loss_treated_as_tamper = checkpoint_missing_detected and (
            continuity_anomaly_ready or self._contains_any_key(
                latest_trace_payload,
                candidate_keys=("checkpoint_missing", "checkpoint_loss_detected"),
            )
        )
        local_lock_mode_ready = trust_state == "UNTRUSTED"
        sensitive_tool_blocked = self._latest_console_status in {401, 403, 409, 423}
        external_anchor_divergence_ready = all(
            (
                divergence_probe.get("trust_state") == "DIVERGED",
                divergence_probe.get("recovery_required") is True,
            ),
        )
        rebuilt_chain_recovery_gate_ready = all(
            (
                bool(rebuilt_chain_probe),
                rebuilt_chain_probe.get("recovery_required") is True,
                rebuilt_chain_probe.get("trust_state") != "ALIGNED",
            ),
        )
        overview_client = self._find_client_state(
            security_center_overview,
            client_id=request.authenticated_employee.authenticated_session_id,
        )
        backend_api_projection_ready = all(
            (
                security_center_timeline.get("client_id") == request.authenticated_employee.authenticated_session_id,
                security_center_timeline.get("recovery_required") is True,
                security_center_timeline.get("trust_state") == "UNTRUSTED",
            ),
        )
        operator_web_projection_ready = all(
            (
                backend_api_projection_ready,
                "Security Center Operator Web" in security_center_web_html,
                "Hash-break curve chart" in security_center_web_html,
                "renderTimeline" in security_center_web_app,
                "/security-center/v1/operator/timelines/" in security_center_web_app,
            ),
        )
        hash_break_curve_chart_ready = all(
            (
                operator_web_projection_ready,
                bool(security_center_timeline.get("local_hash_curve")),
                bool(security_center_timeline.get("cloud_shadow_curve")),
                "timeline-chart" in security_center_web_html,
            ),
        )
        hash_break_fork_point_ready = bool(
            (security_center_timeline.get("fork_point") or {}).get("event_id"),
        )
        cloud_recovery_projection_ready = all(
            (
                backend_api_projection_ready,
                isinstance(overview_client, dict),
                overview_client.get("trust_state") == "UNTRUSTED",
            ),
        )
        security_center_clear_blocked = all(
            (
                backend_api_projection_ready,
                isinstance(overview_client, dict),
                overview_client.get("recovery_required") is True,
                overview_client.get("trust_state") == "UNTRUSTED",
                overview_client.get("gap_status") != "CLEAR",
                overview_client.get("recovery_gate_status") != "CLEAR",
            ),
        )
        recovery_handshake_ready = self._contains_any_key(
            latest_trace_payload,
            candidate_keys=(
                "resume_handshake_status",
                "cloud_anchor_hash",
                "recovery_required",
                "trusted_hash_alignment",
            ),
        )

        failure_reasons: list[str] = []
        if not baseline_cloud_anchor_ready:
            failure_reasons.append(
                "Baseline_Cloud_Anchor_Missing: before tamper, the Security "
                "Center did not hold a non-bootstrap trusted anchor for the "
                "live high-risk session, so rebuilt local history could still "
                "hide behind an empty external baseline."
            )
        if not historical_multi_record_baseline_ready:
            failure_reasons.append(
                "Historical_Multi_Record_Baseline_Missing: before tamper, the "
                "live runtime did not materialize at least three committed "
                "high-risk audit records for the same security session."
            )
        if not tampered_record_is_second_non_tail:
            failure_reasons.append(
                "Second_Historical_Record_Tamper_Missing: the OS-level tamper "
                "control point did not edit the second committed non-tail audit "
                "record while leaving a later record in place."
            )
        if not historical_record_tamper_detected:
            failure_reasons.append(
                "Historical_Record_Tamper_Not_Detected: editing the second "
                "committed audit record did not surface a hash-chain or ledger "
                "continuity anomaly before the next high-risk boundary."
            )
        if not continuity_anomaly_ready:
            failure_reasons.append(
                "Continuity_Anomaly_Missing: the live runtime did not surface "
                "one readable continuity anomaly after OS-level audit tamper."
            )
        if not checkpoint_loss_treated_as_tamper:
            failure_reasons.append(
                "Checkpoint_Loss_Not_Treated_As_Tamper: physical checkpoint loss "
                "was not surfaced as tamper evidence during startup or resume."
            )
        if not local_lock_mode_ready:
            failure_reasons.append(
                "UNTRUSTED_State_Missing: the live runtime did not enter explicit "
                "UNTRUSTED state after checkpoint loss or tamper evidence."
            )
        if not sensitive_tool_blocked:
            failure_reasons.append(
                "Sensitive_Tool_Not_Blocked: the resumed high-risk action was "
                "not refused at the business boundary after tamper evidence."
            )
        if not external_anchor_divergence_ready:
            failure_reasons.append(
                "External_Anchor_Divergence_Missing: the cloud-side recovery "
                "handshake did not mark the tampered local anchor as divergent "
                "before resumed work."
            )
        if not rebuilt_chain_recovery_gate_ready:
            failure_reasons.append(
                "Rebuilt_Chain_Recovery_Gate_Missing: a locally reconstructed "
                "chain head that matches the current cloud anchor could still "
                "clear recovery without a missing-gap validation step."
            )
        if not backend_api_projection_ready:
            failure_reasons.append(
                "Security_Center_Backend_Api_Missing: the live runtime did not "
                "surface the cloud-side recovery state through the frozen backend "
                "API service boundary."
            )
        if not operator_web_projection_ready:
            failure_reasons.append(
                "Security_Center_Operator_Web_Missing: the live runtime did not "
                "surface the anomaly and recovery state through the frozen "
                "operator web boundary."
            )
        if not hash_break_curve_chart_ready:
            failure_reasons.append(
                "Hash_Break_Curve_Chart_Missing: the operator web did not "
                "surface a hash-break curve chart for the local and cloud "
                "shadow hashes."
            )
        if not hash_break_fork_point_ready:
            failure_reasons.append(
                "Hash_Break_Fork_Point_Missing: the operator web did not "
                "mark the exact fork point where local and cloud shadow hashes "
                "diverged."
            )
        if not cloud_recovery_projection_ready:
            failure_reasons.append(
                "Cloud_Recovery_Projection_Missing: the edge runtime did not "
                "emit any cloud-facing anomaly or recovery projection artifact."
            )
        if not security_center_clear_blocked:
            failure_reasons.append(
                "Security_Center_Clear_State_Not_Blocked: after historical "
                "audit-record tamper, the Security Center backend or operator "
                "projection did not remain recovery-required/UNTRUSTED and "
                "therefore could still appear CLEAR before cloud validation."
            )
        if not recovery_handshake_ready:
            failure_reasons.append(
                "Recovery_Handshake_Missing: the live runtime does not yet "
                "prove a first-ask-then-upload recovery handshake before resume."
            )

        return AuditIntegrityLockdownObservation(
            tampered_artifact_path=tampered_artifact_path,
            baseline_cloud_anchor_ready=baseline_cloud_anchor_ready,
            historical_multi_record_baseline_ready=historical_multi_record_baseline_ready,
            tampered_record_is_second_non_tail=tampered_record_is_second_non_tail,
            historical_record_tamper_detected=historical_record_tamper_detected,
            continuity_anomaly_ready=continuity_anomaly_ready,
            checkpoint_loss_treated_as_tamper=checkpoint_loss_treated_as_tamper,
            local_lock_mode_ready=local_lock_mode_ready,
            sensitive_tool_blocked=sensitive_tool_blocked,
            external_anchor_divergence_ready=external_anchor_divergence_ready,
            rebuilt_chain_recovery_gate_ready=rebuilt_chain_recovery_gate_ready,
            backend_api_projection_ready=backend_api_projection_ready,
            operator_web_projection_ready=operator_web_projection_ready,
            hash_break_curve_chart_ready=hash_break_curve_chart_ready,
            hash_break_fork_point_ready=hash_break_fork_point_ready,
            cloud_recovery_projection_ready=cloud_recovery_projection_ready,
            recovery_handshake_ready=recovery_handshake_ready,
            security_center_clear_blocked=security_center_clear_blocked,
            failure_reasons=tuple(failure_reasons),
        )

    def render_audit_integrity_lockdown_failure_report(
        self,
        *,
        tamper_recovery_attempt: AuditIntegrityTamperRequest,
        lockdown_observation: AuditIntegrityLockdownObservation,
    ) -> str:
        lines = ['category="Audit_Integrity_Lockdown_Gap"']
        for failure in dict.fromkeys(lockdown_observation.failure_reasons):
            lines.append(f"- {failure}")
        lines.append("employee_id=" + tamper_recovery_attempt.authenticated_employee.employee_id)
        lines.append("sensitive_tool_name=" + tamper_recovery_attempt.sensitive_tool_name)
        lines.append(
            "baseline_high_risk_action_count="
            + str(len(tamper_recovery_attempt.baseline_high_risk_action_labels)),
        )
        lines.append(
            "tampered_record_position_from_start="
            + str(tamper_recovery_attempt.tampered_record_position_from_start),
        )
        lines.append("security_center_backend_api_name=" + tamper_recovery_attempt.security_center_backend_api_name)
        lines.append("security_center_operator_web_name=" + tamper_recovery_attempt.security_center_operator_web_name)
        lines.append("hash_break_curve_chart_name=" + tamper_recovery_attempt.hash_break_curve_chart_name)
        lines.append("tampered_artifact_path=" + lockdown_observation.tampered_artifact_path)
        lines.append(
            "runtime_console_status="
            + (
                str(self._latest_console_status)
                if self._latest_console_status is not None
                else "<missing>"
            ),
        )
        if self._latest_console_error:
            lines.append("runtime_console_error=" + self._latest_console_error)
        lines.append("runtime_working_dir=" + str(self._app_server.working_dir))
        return "\n".join(lines)

    def verify_normal_offline_reconnect_clears_without_gap_recovery(
        self,
        request: NormalOfflineReconnectRequest,
    ) -> NormalOfflineReconnectObservation:
        if self._app_server.startup_error is not None:
            return NormalOfflineReconnectObservation(
                baseline_client_registration_ready=False,
                trusted_audit_head_ready=False,
                normal_offline_control_point_ready=False,
                runtime_restarted_before_lease_expiry=False,
                backend_clear_projection_ready=False,
                operator_web_clear_projection_ready=False,
                ordinary_model_access_ready=False,
                no_gap_validation_required=False,
                model_access_status=None,
                baseline_client_id=None,
                baseline_trust_state=None,
                post_reconnect_trust_state=None,
                post_reconnect_gap_status=None,
                post_reconnect_recovery_gate_status=None,
                post_reconnect_recovery_required=None,
                failure_reasons=(
                    "Real_Runtime_Bootstrap_Blocking_Dependency: the real app "
                    "subprocess could not finish startup, so sec-e2e-028 could "
                    "not drive a live normal-offline reconnect flow.",
                ),
            )

        before_trace_names = {path.name for path in self._trace_files()}
        self._submit_console_prompt(
            user_id=request.authenticated_employee.employee_id,
            session_id=request.authenticated_employee.authenticated_session_id,
            prompt=(
                "Establish a trusted audit head for normal QwenPaw model "
                "access before a graceful offline reconnect."
            ),
        )
        self._collect_runtime_artifacts(
            session_id=request.authenticated_employee.authenticated_session_id,
            before_trace_names=before_trace_names,
        )
        baseline_access_status = self._latest_console_status
        baseline_overview, baseline_client = self._poll_security_center_client_projection(
            requested_client_id=request.authenticated_employee.authenticated_session_id,
        )
        baseline_client_id = self._client_lookup_id(
            baseline_client,
            fallback=request.authenticated_employee.authenticated_session_id,
        )
        baseline_timeline = self._read_security_center_api_json(
            f"/security-center/v1/operator/timelines/{quote(baseline_client_id, safe='')}",
        ) if baseline_client_id else {}
        baseline_trust_state = self._find_first_scalar(
            baseline_timeline,
            keys=("trust_state",),
        ) or self._find_first_scalar(
            baseline_client if isinstance(baseline_client, dict) else {},
            keys=("trust_state",),
        )
        baseline_gap_status = self._find_first_scalar(
            baseline_timeline,
            keys=("gap_status",),
        ) or self._find_first_scalar(
            baseline_client if isinstance(baseline_client, dict) else {},
            keys=("gap_status",),
        )
        baseline_recovery_gate_status = self._find_first_scalar(
            baseline_timeline,
            keys=("recovery_gate_status",),
        ) or self._find_first_scalar(
            baseline_client if isinstance(baseline_client, dict) else {},
            keys=("recovery_gate_status",),
        )
        baseline_recovery_required = self._find_first_scalar(
            baseline_timeline,
            keys=("recovery_required",),
        )
        if baseline_recovery_required is None:
            baseline_recovery_required = self._find_first_scalar(
                baseline_client if isinstance(baseline_client, dict) else {},
                keys=("recovery_required",),
            )

        baseline_client_registration_ready = isinstance(baseline_client, dict)
        trusted_audit_head_ready = all(
            (
                baseline_client_registration_ready,
                baseline_access_status == 200,
                str(baseline_trust_state or "") in {"ALIGNED", "TRUSTED"},
                str(baseline_gap_status or "") == "CLEAR",
                str(baseline_recovery_gate_status or "") == "CLEAR",
                baseline_recovery_required is False,
            ),
        )

        restart_ready, restarted_before_expiry, restart_error = self._restart_runtime_normally_before_lease_expiry(
            baseline_client=baseline_client if isinstance(baseline_client, dict) else {},
            baseline_timeline=baseline_timeline,
        )
        normal_offline_control_point_ready = restart_ready and not restart_error

        before_reconnect_trace_names = {path.name for path in self._trace_files()}
        self._submit_console_prompt(
            user_id=request.authenticated_employee.employee_id,
            session_id=request.authenticated_employee.authenticated_session_id,
            prompt=(
                "Resume ordinary model access after a normal offline window "
                "that stayed inside the lease boundary."
            ),
        )
        self._collect_runtime_artifacts(
            session_id=request.authenticated_employee.authenticated_session_id,
            before_trace_names=before_reconnect_trace_names,
        )
        model_access_status = self._latest_console_status

        post_reconnect_timeline, post_reconnect_client = self._poll_security_center_clear_projection(
            client_id=baseline_client_id or request.authenticated_employee.authenticated_session_id,
        )
        post_reconnect_trust_state = self._find_first_scalar(
            post_reconnect_timeline,
            keys=("trust_state",),
        ) or self._find_first_scalar(
            post_reconnect_client if isinstance(post_reconnect_client, dict) else {},
            keys=("trust_state",),
        )
        post_reconnect_gap_status = self._find_first_scalar(
            post_reconnect_timeline,
            keys=("gap_status",),
        ) or self._find_first_scalar(
            post_reconnect_client if isinstance(post_reconnect_client, dict) else {},
            keys=("gap_status",),
        )
        post_reconnect_recovery_gate_status = self._find_first_scalar(
            post_reconnect_timeline,
            keys=("recovery_gate_status",),
        ) or self._find_first_scalar(
            post_reconnect_client if isinstance(post_reconnect_client, dict) else {},
            keys=("recovery_gate_status",),
        )
        post_reconnect_recovery_required = self._find_first_scalar(
            post_reconnect_timeline,
            keys=("recovery_required",),
        )
        if post_reconnect_recovery_required is None:
            post_reconnect_recovery_required = self._find_first_scalar(
                post_reconnect_client if isinstance(post_reconnect_client, dict) else {},
                keys=("recovery_required",),
            )
        divergence_reason = self._find_first_scalar(
            post_reconnect_timeline,
            keys=("divergence_reason",),
        ) or self._find_first_scalar(
            post_reconnect_client if isinstance(post_reconnect_client, dict) else {},
            keys=("divergence_reason",),
        )
        security_center_web_html = self._read_security_center_web_text("/")
        security_center_web_app = self._read_security_center_web_text("/app.js")

        backend_clear_projection_ready = all(
            (
                isinstance(post_reconnect_timeline, dict),
                str(post_reconnect_trust_state or "") in {"ALIGNED", "TRUSTED"},
                post_reconnect_gap_status == "CLEAR",
                post_reconnect_recovery_gate_status == "CLEAR",
                post_reconnect_recovery_required is False,
            ),
        )
        operator_web_clear_projection_ready = all(
            (
                backend_clear_projection_ready,
                "Security Center Operator Web" in security_center_web_html,
                "renderTimeline" in security_center_web_app,
                "gap_status" in security_center_web_app,
                "recovery_gate_status" in security_center_web_app,
                "recovery_required" in security_center_web_app,
            ),
        )
        ordinary_model_access_ready = model_access_status == 200
        no_gap_validation_required = all(
            (
                backend_clear_projection_ready,
                divergence_reason in (None, ""),
                post_reconnect_gap_status not in {"REQUIRED", "GAP_VALIDATION_REQUIRED"},
                post_reconnect_recovery_gate_status not in {"OPEN", "REQUIRED"},
            ),
        )

        failure_reasons: list[str] = []
        if not baseline_client_registration_ready:
            failure_reasons.append(
                "Normal_Reconnect_Client_Registration_Missing: the Security "
                "Center backend did not project a canonical client before the "
                "normal offline control point."
            )
        if not trusted_audit_head_ready:
            failure_reasons.append(
                "Trusted_Audit_Head_Missing: the baseline online client did not "
                "show ALIGNED or TRUSTED with gap_status=CLEAR, "
                "recovery_gate_status=CLEAR, recovery_required=false, and "
                "ordinary model access 200 before offline."
            )
        if not normal_offline_control_point_ready:
            failure_reasons.append(
                "Normal_Offline_Control_Point_Missing: the harness could not "
                "gracefully stop and restart the same QwenPaw runtime for the "
                "normal offline reconnect scenario."
            )
        if not restarted_before_expiry:
            failure_reasons.append(
                "Lease_Boundary_Crossed_By_Test_Setup: the normal offline "
                "control point did not prove that reconnect occurred before "
                "lease expiry; sec-e2e-028 must not exercise sec-e2e-027's "
                "expired-lease branch."
            )
        if not backend_clear_projection_ready:
            failure_reasons.append(
                "Normal_Reconnect_Backend_Clear_State_Missing: after normal "
                "offline reconnect, Security Center backend did not project "
                "ALIGNED|TRUSTED with gap_status=CLEAR, "
                "recovery_gate_status=CLEAR, and recovery_required=false."
            )
        if not operator_web_clear_projection_ready:
            failure_reasons.append(
                "Normal_Reconnect_Operator_Web_Clear_State_Missing: after "
                "normal offline reconnect, the operator web boundary did not "
                "remain wired to display backend CLEAR trust and recovery fields."
            )
        if not ordinary_model_access_ready:
            failure_reasons.append(
                "Normal_Reconnect_Model_Access_200_Missing: ordinary model "
                "access did not return HTTP 200 after normal offline reconnect."
            )
        if not no_gap_validation_required:
            failure_reasons.append(
                "Normal_Reconnect_Gap_Validation_False_Positive: the normal "
                "offline reconnect path still surfaced REQUIRED, OPEN, "
                "missing_gap_proof, or another recovery-gated state without a "
                "real lease-expiry, tamper, missing-sequence, clone, or replay "
                "condition."
            )
        if restart_error:
            failure_reasons.append("Normal_Reconnect_Runtime_Restart_Error: " + restart_error)

        return NormalOfflineReconnectObservation(
            baseline_client_registration_ready=baseline_client_registration_ready,
            trusted_audit_head_ready=trusted_audit_head_ready,
            normal_offline_control_point_ready=normal_offline_control_point_ready,
            runtime_restarted_before_lease_expiry=restarted_before_expiry,
            backend_clear_projection_ready=backend_clear_projection_ready,
            operator_web_clear_projection_ready=operator_web_clear_projection_ready,
            ordinary_model_access_ready=ordinary_model_access_ready,
            no_gap_validation_required=no_gap_validation_required,
            model_access_status=model_access_status,
            baseline_client_id=baseline_client_id,
            baseline_trust_state=str(baseline_trust_state) if baseline_trust_state is not None else None,
            post_reconnect_trust_state=(
                str(post_reconnect_trust_state)
                if post_reconnect_trust_state is not None
                else None
            ),
            post_reconnect_gap_status=(
                str(post_reconnect_gap_status)
                if post_reconnect_gap_status is not None
                else None
            ),
            post_reconnect_recovery_gate_status=(
                str(post_reconnect_recovery_gate_status)
                if post_reconnect_recovery_gate_status is not None
                else None
            ),
            post_reconnect_recovery_required=(
                bool(post_reconnect_recovery_required)
                if isinstance(post_reconnect_recovery_required, bool)
                else None
            ),
            failure_reasons=tuple(failure_reasons),
        )

    def render_normal_offline_reconnect_failure_report(
        self,
        *,
        normal_reconnect_request: NormalOfflineReconnectRequest,
        normal_reconnect_observation: NormalOfflineReconnectObservation,
    ) -> str:
        lines = ['category="Normal_Offline_Reconnect_Clear_State_Gap"']
        for failure in dict.fromkeys(normal_reconnect_observation.failure_reasons):
            lines.append(f"- {failure}")
        lines.append("employee_id=" + normal_reconnect_request.authenticated_employee.employee_id)
        lines.append("normal_offline_action_label=" + normal_reconnect_request.normal_offline_action_label)
        lines.append("restored_model_access_label=" + normal_reconnect_request.restored_model_access_label)
        lines.append("security_center_backend_api_name=" + normal_reconnect_request.security_center_backend_api_name)
        lines.append("security_center_operator_web_name=" + normal_reconnect_request.security_center_operator_web_name)
        lines.append("baseline_client_id=" + (normal_reconnect_observation.baseline_client_id or "<missing>"))
        lines.append("baseline_trust_state=" + (normal_reconnect_observation.baseline_trust_state or "<missing>"))
        lines.append(
            "post_reconnect_trust_state="
            + (normal_reconnect_observation.post_reconnect_trust_state or "<missing>")
        )
        lines.append(
            "post_reconnect_gap_status="
            + (normal_reconnect_observation.post_reconnect_gap_status or "<missing>")
        )
        lines.append(
            "post_reconnect_recovery_gate_status="
            + (normal_reconnect_observation.post_reconnect_recovery_gate_status or "<missing>")
        )
        lines.append(
            "post_reconnect_recovery_required="
            + (
                str(normal_reconnect_observation.post_reconnect_recovery_required)
                if normal_reconnect_observation.post_reconnect_recovery_required is not None
                else "<missing>"
            )
        )
        lines.append(
            "model_access_status="
            + (
                str(normal_reconnect_observation.model_access_status)
                if normal_reconnect_observation.model_access_status is not None
                else "<missing>"
            )
        )
        if self._latest_console_error:
            lines.append("runtime_console_error=" + self._latest_console_error)
        lines.append("runtime_working_dir=" + str(self._app_server.working_dir))
        return "\n".join(lines)

    def verify_lease_expiry_blocks_untrusted_rejoin_until_gap_sync(
        self,
        request: LeaseExpiryRecoveryRequest,
    ) -> LeaseExpiryRecoveryObservation:
        if self._app_server.startup_error is not None:
            try:
                version_response = self._app_server.client.get(
                    f"{self._app_server.base_url}/api/version",
                    timeout=_HTTP_TIMEOUT,
                )
            except httpx.HTTPError:
                version_response = None
            if version_response is None or version_response.status_code != 200:
                return LeaseExpiryRecoveryObservation(
                    baseline_client_registration_ready=False,
                    heartbeat_projection_ready=False,
                    pre_recovery_lease_monitor_projection_ready=False,
                    pre_recovery_backend_api_projection_ready=False,
                    pre_recovery_operator_web_projection_ready=False,
                    pre_recovery_reconnect_denied_ready=False,
                    recovery_control_point_ready=False,
                    post_recovery_backend_api_projection_ready=False,
                    post_recovery_operator_web_projection_ready=False,
                    post_recovery_model_access_ready=False,
                    pre_recovery_console_status=None,
                    post_recovery_console_status=None,
                    pre_recovery_trust_state=None,
                    post_recovery_trust_state=None,
                    failure_reasons=(
                        "Real_Runtime_Bootstrap_Blocking_Dependency: the real app "
                        "subprocess could not finish startup, so sec-e2e-027 could "
                        "not drive a live lease-expiry recovery flow.",
                    ),
                )

        before_trace_names = {path.name for path in self._trace_files()}
        self._submit_console_prompt(
            user_id=request.authenticated_employee.employee_id,
            session_id=request.authenticated_employee.authenticated_session_id,
            prompt=(
                "Warm the runtime for lease heartbeat monitoring before the "
                "Security Center lease window expires."
            ),
        )
        self._collect_runtime_artifacts(
            session_id=request.authenticated_employee.authenticated_session_id,
            before_trace_names=before_trace_names,
        )

        initial_trace_payload = self._load_latest_trace_payload()
        overview_before_rejoin = self._read_security_center_api_json(
            "/security-center/v1/operator/overview",
        )
        timeline_before_rejoin = self._read_security_center_api_json(
            f"/security-center/v1/operator/timelines/{quote(request.authenticated_employee.authenticated_session_id, safe='')}",
        )
        overview_client_before_rejoin = self._find_client_state(
            overview_before_rejoin,
            client_id=request.authenticated_employee.authenticated_session_id,
        )

        rejoin_prompt = (
            "Resume normal model access for the previously trusted device "
            "after the lease window elapsed, without providing missing-gap "
            "verification evidence."
        )
        before_rejoin_trace_names = {path.name for path in self._trace_files()}
        self._submit_console_prompt(
            user_id=request.authenticated_employee.employee_id,
            session_id=request.authenticated_employee.authenticated_session_id,
            prompt=rejoin_prompt,
        )
        self._collect_runtime_artifacts(
            session_id=request.authenticated_employee.authenticated_session_id,
            before_trace_names=before_rejoin_trace_names,
        )
        pre_recovery_console_status = self._latest_console_status

        latest_trace_payload = self._load_latest_trace_payload()
        overview_after_rejoin = self._read_security_center_api_json(
            "/security-center/v1/operator/overview",
        )
        timeline_after_rejoin = self._read_security_center_api_json(
            f"/security-center/v1/operator/timelines/{quote(request.authenticated_employee.authenticated_session_id, safe='')}",
        )
        security_center_web_html = self._read_security_center_web_text("/")
        security_center_web_app = self._read_security_center_web_text("/app.js")
        overview_client_after_rejoin = self._find_client_state(
            overview_after_rejoin,
            client_id=request.authenticated_employee.authenticated_session_id,
        )
        pre_recovery_trust_state = self._find_first_scalar(
            timeline_after_rejoin,
            keys=("trust_state",),
        ) or self._find_first_scalar(
            overview_client_after_rejoin if isinstance(overview_client_after_rejoin, dict) else {},
            keys=("trust_state",),
        )

        recovery_handshake = self._attempt_missing_gap_verification(
            session_id=request.authenticated_employee.authenticated_session_id,
        )
        timeline_after_recovery = self._read_security_center_api_json(
            f"/security-center/v1/operator/timelines/{quote(request.authenticated_employee.authenticated_session_id, safe='')}",
        )
        overview_after_recovery = self._read_security_center_api_json(
            "/security-center/v1/operator/overview",
        )
        overview_client_after_recovery = self._find_client_state(
            overview_after_recovery,
            client_id=request.authenticated_employee.authenticated_session_id,
        )
        post_recovery_trust_state = self._find_first_scalar(
            timeline_after_recovery,
            keys=("trust_state",),
        ) or self._find_first_scalar(
            overview_client_after_recovery if isinstance(overview_client_after_recovery, dict) else {},
            keys=("trust_state",),
        )

        before_restored_model_access_trace_names = {path.name for path in self._trace_files()}
        self._submit_console_prompt(
            user_id=request.authenticated_employee.employee_id,
            session_id=request.authenticated_employee.authenticated_session_id,
            prompt=(
                "Resume normal model access for the previously trusted device "
                "after the lease window elapsed, with missing-gap verification "
                "evidence completed."
            ),
        )
        self._collect_runtime_artifacts(
            session_id=request.authenticated_employee.authenticated_session_id,
            before_trace_names=before_restored_model_access_trace_names,
        )
        post_recovery_console_status = self._latest_console_status

        post_recovery_timeline_after_access = self._read_security_center_api_json(
            f"/security-center/v1/operator/timelines/{quote(request.authenticated_employee.authenticated_session_id, safe='')}",
        )
        post_recovery_overview_after_access = self._read_security_center_api_json(
            "/security-center/v1/operator/overview",
        )
        post_recovery_client_after_access = self._find_client_state(
            post_recovery_overview_after_access,
            client_id=request.authenticated_employee.authenticated_session_id,
        )
        if post_recovery_client_after_access is not None:
            overview_client_after_recovery = post_recovery_client_after_access
        if isinstance(post_recovery_timeline_after_access, dict) and post_recovery_timeline_after_access.get("client_id"):
            timeline_after_recovery = post_recovery_timeline_after_access
            post_recovery_trust_state = self._find_first_scalar(
                timeline_after_recovery,
                keys=("trust_state",),
            ) or post_recovery_trust_state

        baseline_client_registration_ready = isinstance(
            overview_client_before_rejoin,
            dict,
        ) or isinstance(timeline_before_rejoin, dict)
        heartbeat_projection_ready = self._contains_any_key(
            initial_trace_payload,
            candidate_keys=(
                "heartbeat_emitted_at",
                "heartbeat_interval_seconds",
                "security_heartbeat",
                "lease_client_id",
            ),
        ) or self._contains_any_key(
            overview_client_before_rejoin if isinstance(overview_client_before_rejoin, dict) else {},
            candidate_keys=("last_heartbeat_at", "lease_expires_at", "lease_ttl_seconds"),
        )
        pre_recovery_lease_monitor_projection_ready = all(
            (
                isinstance(timeline_after_rejoin, dict),
                pre_recovery_trust_state == "UNTRUSTED",
                timeline_after_rejoin.get("recovery_required") is True,
            ),
        )
        pre_recovery_backend_api_projection_ready = all(
            (
                isinstance(overview_client_after_rejoin, dict),
                isinstance(timeline_after_rejoin, dict),
                timeline_after_rejoin.get("client_id") == request.authenticated_employee.authenticated_session_id,
            ),
        )
        pre_recovery_operator_web_projection_ready = all(
            (
                pre_recovery_backend_api_projection_ready,
                "Security Center Operator Web" in security_center_web_html,
                "UNTRUSTED" in security_center_web_html,
                "renderTimeline" in security_center_web_app,
                "/security-center/v1/operator/timelines/" in security_center_web_app,
            ),
        )
        pre_recovery_reconnect_denied_ready = pre_recovery_console_status in {401, 403, 409, 423}
        recovery_control_point_ready = all(
            (
                isinstance(recovery_handshake, dict),
                recovery_handshake.get("trust_state") in {"ALIGNED", "TRUSTED"},
                recovery_handshake.get("recovery_required") is False,
            ),
        )
        post_recovery_backend_api_projection_ready = all(
            (
                isinstance(overview_client_after_recovery, dict),
                isinstance(timeline_after_recovery, dict),
                timeline_after_recovery.get("client_id") == request.authenticated_employee.authenticated_session_id,
            ),
        )
        post_recovery_operator_web_projection_ready = all(
            (
                post_recovery_backend_api_projection_ready,
                "Security Center Operator Web" in security_center_web_html,
                "renderTimeline" in security_center_web_app,
                "/security-center/v1/operator/timelines/" in security_center_web_app,
            ),
        )
        post_recovery_model_access_ready = all(
            (
                timeline_after_recovery.get("recovery_required") is False,
                str(post_recovery_trust_state or "") in {"ALIGNED", "TRUSTED"},
                post_recovery_console_status == 200,
            ),
        )

        failure_reasons: list[str] = []
        if not baseline_client_registration_ready:
            failure_reasons.append(
                "Lease_Monitor_Client_Registration_Missing: the separate "
                "Security Center boundary did not register any client record "
                "for the live device session before lease-expiry evaluation."
            )
        if not heartbeat_projection_ready:
            failure_reasons.append(
                "Lease_Heartbeat_Projection_Missing: the live runtime did not "
                "emit any heartbeat or lease TTL evidence that the Security "
                "Center lease monitor can evaluate."
            )
        if not pre_recovery_lease_monitor_projection_ready:
            failure_reasons.append(
                "UNTRUSTED_Lease_Downgrade_Missing: the Security Center lease "
                "monitor did not downgrade the client to UNTRUSTED after the "
                "expected heartbeat gap."
            )
        if not pre_recovery_backend_api_projection_ready:
            failure_reasons.append(
                "Security_Center_Backend_Api_Missing: the live runtime did not "
                "surface lease-expiry trust state through the frozen backend "
                "API service boundary."
            )
        if not pre_recovery_operator_web_projection_ready:
            failure_reasons.append(
                "Security_Center_Operator_Web_Missing: the operator web did "
                "not surface the UNTRUSTED device recovery view for the lease "
                "expiry scenario."
            )
        if not pre_recovery_reconnect_denied_ready:
            failure_reasons.append(
                "Model_Access_Reconnect_Gate_Missing: the reconnecting device "
                "was not denied at model-access scope before missing-gap "
                "verification completed."
            )
        if not recovery_control_point_ready:
            failure_reasons.append(
                "Recovery_Control_Point_Missing: the repository does not yet "
                "expose a controlled missing-gap verification step that moves "
                "sec-e2e-027 from the denied rejoin frame into a distinct "
                "post-recovery observation frame."
            )
        if not post_recovery_backend_api_projection_ready:
            failure_reasons.append(
                "Post_Recovery_Backend_Api_Projection_Missing: the separate "
                "Security Center backend API does not yet project a distinct "
                "post-recovery trust-state frame for sec-e2e-027."
            )
        if not post_recovery_operator_web_projection_ready:
            failure_reasons.append(
                "Post_Recovery_Operator_Web_Projection_Missing: the operator "
                "web does not yet surface a distinct post-recovery trust-state "
                "frame for sec-e2e-027."
            )
        if not post_recovery_model_access_ready:
            failure_reasons.append(
                "Post_Recovery_Model_Access_Restore_Missing: the repository "
                "does not yet prove that normal model access is restored only "
                "after continuity has been validated."
            )

        return LeaseExpiryRecoveryObservation(
            baseline_client_registration_ready=baseline_client_registration_ready,
            heartbeat_projection_ready=heartbeat_projection_ready,
            pre_recovery_lease_monitor_projection_ready=pre_recovery_lease_monitor_projection_ready,
            pre_recovery_backend_api_projection_ready=pre_recovery_backend_api_projection_ready,
            pre_recovery_operator_web_projection_ready=pre_recovery_operator_web_projection_ready,
            pre_recovery_reconnect_denied_ready=pre_recovery_reconnect_denied_ready,
            recovery_control_point_ready=recovery_control_point_ready,
            post_recovery_backend_api_projection_ready=post_recovery_backend_api_projection_ready,
            post_recovery_operator_web_projection_ready=post_recovery_operator_web_projection_ready,
            post_recovery_model_access_ready=post_recovery_model_access_ready,
            pre_recovery_console_status=pre_recovery_console_status,
            post_recovery_console_status=post_recovery_console_status,
            pre_recovery_trust_state=str(pre_recovery_trust_state) if pre_recovery_trust_state is not None else None,
            post_recovery_trust_state=str(post_recovery_trust_state) if post_recovery_trust_state is not None else None,
            failure_reasons=tuple(failure_reasons),
        )

    def render_lease_expiry_failure_report(
        self,
        *,
        lease_expiry_request: LeaseExpiryRecoveryRequest,
        lease_expiry_observation: LeaseExpiryRecoveryObservation,
    ) -> str:
        lines = ['category="Lease_Expiry_Active_Defense_Gap"']
        for failure in dict.fromkeys(lease_expiry_observation.failure_reasons):
            lines.append(f"- {failure}")
        lines.append("employee_id=" + lease_expiry_request.authenticated_employee.employee_id)
        lines.append("lease_monitor_name=" + lease_expiry_request.lease_monitor_name)
        lines.append("security_center_backend_api_name=" + lease_expiry_request.security_center_backend_api_name)
        lines.append("security_center_operator_web_name=" + lease_expiry_request.security_center_operator_web_name)
        lines.append("missing_gap_verification_label=" + lease_expiry_request.missing_gap_verification_label)
        lines.append("restored_model_access_label=" + lease_expiry_request.restored_model_access_label)
        lines.append(
            "pre_recovery_trust_state="
            + (lease_expiry_observation.pre_recovery_trust_state or "<missing>")
        )
        lines.append(
            "post_recovery_trust_state="
            + (lease_expiry_observation.post_recovery_trust_state or "<missing>")
        )
        lines.append(
            "pre_recovery_console_status="
            + (
                str(lease_expiry_observation.pre_recovery_console_status)
                if lease_expiry_observation.pre_recovery_console_status is not None
                else "<missing>"
            ),
        )
        lines.append(
            "post_recovery_console_status="
            + (
                str(lease_expiry_observation.post_recovery_console_status)
                if lease_expiry_observation.post_recovery_console_status is not None
                else "<missing>"
            ),
        )
        if self._latest_console_error:
            lines.append("runtime_console_error=" + self._latest_console_error)
        lines.append("runtime_working_dir=" + str(self._app_server.working_dir))
        return "\n".join(lines)

    def _attempt_missing_gap_verification(self, *, session_id: str) -> dict[str, Any]:
        latest_trace_payload = self._load_latest_trace_payload()
        gap_proof = self._build_gap_proof(session_id=session_id)
        local_hash = self._find_first_scalar(
            latest_trace_payload,
            keys=("current_edge_reported_hash", "current_hash", "cloud_anchor_hash"),
        )
        checkpoint_hash = self._find_first_scalar(
            latest_trace_payload,
            keys=("last_trusted_anchor_hash", "cloud_anchor_hash", "current_hash"),
        )
        local_sequence = self._coerce_int(
            self._find_first_scalar(
                latest_trace_payload,
                keys=("current_edge_reported_sequence", "event_sequence", "last_trusted_sequence"),
            ),
        )
        checkpoint_sequence = self._coerce_int(
            self._find_first_scalar(
                latest_trace_payload,
                keys=("last_trusted_sequence", "current_edge_reported_sequence", "event_sequence"),
            ),
        )
        anchored_event_id = self._find_first_scalar(
            latest_trace_payload,
            keys=("current_edge_reported_anchor_event_id", "anchored_event_id", "last_trusted_anchor_event_id"),
        )
        checkpoint_anchor_id = self._find_first_scalar(
            latest_trace_payload,
            keys=("last_trusted_anchor_event_id", "current_edge_reported_anchor_event_id", "anchored_event_id"),
        )
        if gap_proof:
            local_hash = gap_proof.get("head_hash") or local_hash
            checkpoint_hash = gap_proof.get("base_anchor_hash") or checkpoint_hash
            local_sequence = self._coerce_int(gap_proof.get("head_sequence")) or local_sequence
            checkpoint_sequence = self._coerce_int(gap_proof.get("base_sequence")) or checkpoint_sequence
            anchored_event_id = gap_proof.get("head_anchor_event_id") or anchored_event_id
            checkpoint_anchor_id = gap_proof.get("base_anchor_event_id") or checkpoint_anchor_id
        if not isinstance(local_hash, str) or not local_hash:
            return {}
        return self._post_security_center_api_json(
            "/security-center/v1/recovery/handshake",
            json={
                "client_id": session_id,
                "trace_id": f"explicit-gap-verification::{session_id}",
                "local_hash": local_hash,
                "checkpoint_hash": checkpoint_hash or local_hash,
                "local_sequence": local_sequence,
                "checkpoint_sequence": checkpoint_sequence,
                "anchored_event_id": anchored_event_id,
                "checkpoint_anchor_id": checkpoint_anchor_id or anchored_event_id,
                "gap_proof": gap_proof,
                "requested_at_ns": time.time_ns(),
            },
        )

    def verify_prompt_injection_guard_enforced(
        self,
        attempt: PromptInjectionAttempt,
    ) -> PromptInjectionGuardObservation:
        if self._app_server.startup_error is not None:
            return PromptInjectionGuardObservation(
                tool_boundary_guard_ready=False,
                missing_trusted_context_rejected=False,
                durable_rejected_event_ready=False,
                backend_api_rejection_ready=False,
                operator_web_rejection_ready=False,
                nonce_voucher_ready=False,
                realtime_push_channel_ready=False,
                realtime_red_alert_ready=False,
                observed_alert_latency_ms=None,
                security_center_mirror_ready=False,
                security_rejection_nonce=None,
                security_rejection_nonce_trace_bound=False,
                failure_reasons=(
                    "Real_Runtime_Bootstrap_Blocking_Dependency: the real app "
                    "subprocess could not finish startup, so sec-e2e-021 could "
                    "not drive a live prompt-injection attempt.",
                ),
            )

        before_trace_names = {path.name for path in self._trace_files()}
        self._submit_console_prompt(
            user_id=attempt.authenticated_employee.employee_id,
            session_id=attempt.authenticated_employee.authenticated_session_id,
            prompt=attempt.deceptive_instruction_text,
        )
        self._collect_runtime_artifacts(
            session_id=attempt.authenticated_employee.authenticated_session_id,
            before_trace_names=before_trace_names,
        )

        approval_records = self._latest_pending_approvals()
        latest_trace_payload = self._load_latest_trace_payload()
        security_center_overview = self._read_security_center_api_json(
            "/security-center/v1/operator/overview",
        )
        security_rejection_nonce = self._extract_security_rejection_nonce(
            latest_trace_payload=latest_trace_payload,
            approval_records=approval_records,
        )
        rejection_payload = self._read_security_center_api_json(
            f"/security-center/v1/operator/rejections/{quote(security_rejection_nonce, safe='')}",
        ) if security_rejection_nonce else {}
        voucher_payload = self._read_security_center_api_json(
            f"/security-center/v1/operator/vouchers/{quote(security_rejection_nonce, safe='')}",
        ) if security_rejection_nonce else {}
        security_center_web_html = self._read_security_center_web_text("/")
        security_center_web_app = self._read_security_center_web_text("/app.js")
        realtime_stream_ready, realtime_stream_payload = self._security_center_stream_is_ready()
        latest_alert = self._find_alert(
            security_center_overview,
            alert_type="SECURITY_REJECTION",
            client_id=attempt.authenticated_employee.authenticated_session_id,
            nonce=security_rejection_nonce,
        )
        security_rejection_nonce_trace_bound = self._security_rejection_nonce_is_trace_bound(
            latest_trace_payload=latest_trace_payload,
            security_rejection_nonce=security_rejection_nonce,
        )
        tool_boundary_guard_ready = self._find_match(
            latest_trace_payload,
            attempt.targeted_high_risk_tool_name,
        ) or self._contains_any_key(
            latest_trace_payload,
            candidate_keys=("tool_name", "tool_call_id", "guard_decision"),
        )
        explicit_guard_rejection_ready = (
            self._latest_console_status in {401, 403, 409, 423}
            or self._find_match(latest_trace_payload, "rejected")
            or self._find_match(latest_trace_payload, "denied")
            or self._response_body_contains_guard_rejection()
        )
        missing_trusted_context_rejected = (
            security_rejection_nonce is not None and explicit_guard_rejection_ready
        )
        durable_rejected_event_ready = self._contains_any_key(
            latest_trace_payload,
            candidate_keys=(
                "rejection_reason",
                "rejected_event_id",
                "guard_category",
                "decision",
            ),
        ) and not self._find_match(approval_records, attempt.targeted_high_risk_tool_name)
        backend_api_rejection_ready = all(
            (
                rejection_payload.get("nonce") == security_rejection_nonce,
                rejection_payload.get("client_id") == attempt.authenticated_employee.authenticated_session_id,
                rejection_payload.get("tool_name") == attempt.targeted_high_risk_tool_name,
            ),
        )
        operator_web_rejection_ready = all(
            (
                backend_api_rejection_ready,
                "Security Center Operator Web" in security_center_web_html,
                "Rejected-event evidence" in security_center_web_html,
                "Nonce Voucher display" in security_center_web_html,
            ),
        )
        nonce_voucher_ready = (
            security_rejection_nonce is not None
            and voucher_payload.get("nonce") == security_rejection_nonce
            and voucher_payload.get("voucher") == f"Voucher:{security_rejection_nonce}"
        )
        realtime_push_channel_ready = all(
            (
                realtime_stream_ready,
                "EventSource" in security_center_web_app,
                "/security-center/v1/operator/stream" in security_center_web_app,
                "event: ready" in realtime_stream_payload,
            ),
        )
        observed_alert_latency_ms = self._coerce_int(latest_alert.get("alert_latency_ms"))
        realtime_red_alert_ready = (
            realtime_push_channel_ready
            and observed_alert_latency_ms is not None
            and observed_alert_latency_ms < 500
            and latest_alert.get("edge_timestamp_ns") is not None
            and latest_alert.get("severity") == "critical"
            and "Realtime operator alert" in security_center_web_html
        )
        security_center_mirror_ready = all(
            (
                backend_api_rejection_ready,
                self._find_rejection(
                    security_center_overview,
                    client_id=attempt.authenticated_employee.authenticated_session_id,
                    nonce=security_rejection_nonce,
                )
                is not None,
            ),
        )

        failure_reasons: list[str] = []
        if self._latest_console_error:
            failure_reasons.append(
                "Functional_Runtime_Failure_Not_Security_Rejection: the live "
                "request ended with a transport or timeout error, so the harness "
                "cannot treat it as guard enforcement."
            )
        elif isinstance(self._latest_console_status, int) and self._latest_console_status >= 500:
            failure_reasons.append(
                "Functional_Runtime_Failure_Not_Security_Rejection: the live "
                "request returned a 5xx response, which is a runtime failure not "
                "a verifiable High Risk Tool Guard rejection."
            )
        if not tool_boundary_guard_ready:
            failure_reasons.append(
                "Tool_Boundary_Guard_Missing: the live runtime did not emit a "
                "tool-layer interception artifact for the targeted High risk tool."
            )
        if security_rejection_nonce is None:
            failure_reasons.append(
                "Security_Rejection_Nonce_Missing: the live runtime did not "
                "emit a Security_Rejection_Nonce in the HTTP response or durable "
                "audit evidence, so the harness cannot distinguish guard rejection "
                "from a generic functional failure."
            )
        elif not security_rejection_nonce_trace_bound:
            failure_reasons.append(
                "Security_Rejection_Nonce_Not_Trace_Bound: the observed "
                "Security_Rejection_Nonce does not prove a cryptographic binding "
                "to the current trace chain and may be static or replayable."
            )
        if not missing_trusted_context_rejected:
            failure_reasons.append(
                "Missing_Trust_Rejection_Missing: the live runtime did not "
                "reject the deceptive request because trusted provenance and "
                "confirmation were absent with a verifiable guard-issued nonce."
            )
        if not durable_rejected_event_ready:
            failure_reasons.append(
                "Rejected_Event_Missing: the live runtime did not persist a "
                "durable rejected security event for the bypass attempt."
            )
        if not backend_api_rejection_ready:
            failure_reasons.append(
                "Security_Center_Backend_Api_Missing: the live runtime did not "
                "surface rejected-event evidence through the frozen backend API "
                "service boundary."
            )
        if not operator_web_rejection_ready:
            failure_reasons.append(
                "Security_Center_Operator_Web_Missing: the live runtime did not "
                "surface the rejected action through the frozen operator web "
                "boundary."
            )
        if not nonce_voucher_ready:
            failure_reasons.append(
                "Nonce_Voucher_Missing: the operator web did not expose the "
                "Security_Rejection_Nonce as a human-readable voucher for "
                "administrator log verification."
            )
        if not realtime_push_channel_ready:
            failure_reasons.append(
                "Realtime_Push_Channel_Missing: deploy/api did not expose a "
                "Server-Sent Events or WebSocket channel for operator alerting."
            )
        if not realtime_red_alert_ready:
            failure_reasons.append(
                "Realtime_Red_Alert_Missing: the operator web did not surface a "
                "red alert within 500ms of Security_Rejection_Nonce uplink "
                "receipt without manual refresh."
            )
        if not security_center_mirror_ready:
            failure_reasons.append(
                "Security_Center_Mirror_Missing: the live runtime did not "
                "project rejected-event evidence through the cloud-facing seam."
            )

        return PromptInjectionGuardObservation(
            tool_boundary_guard_ready=tool_boundary_guard_ready,
            missing_trusted_context_rejected=missing_trusted_context_rejected,
            durable_rejected_event_ready=durable_rejected_event_ready,
            backend_api_rejection_ready=backend_api_rejection_ready,
            operator_web_rejection_ready=operator_web_rejection_ready,
            nonce_voucher_ready=nonce_voucher_ready,
            realtime_push_channel_ready=realtime_push_channel_ready,
            realtime_red_alert_ready=realtime_red_alert_ready,
            observed_alert_latency_ms=observed_alert_latency_ms,
            security_center_mirror_ready=security_center_mirror_ready,
            security_rejection_nonce=security_rejection_nonce,
            security_rejection_nonce_trace_bound=security_rejection_nonce_trace_bound,
            failure_reasons=tuple(failure_reasons),
        )

    def render_prompt_injection_guard_failure_report(
        self,
        *,
        prompt_injection_attempt: PromptInjectionAttempt,
        guard_observation: PromptInjectionGuardObservation,
    ) -> str:
        lines = ['category="Prompt_Injection_Guard_Gap"']
        for failure in dict.fromkeys(guard_observation.failure_reasons):
            lines.append(f"- {failure}")
        lines.append("employee_id=" + prompt_injection_attempt.authenticated_employee.employee_id)
        lines.append("targeted_high_risk_tool_name=" + prompt_injection_attempt.targeted_high_risk_tool_name)
        lines.append("bypass_narrative_label=" + prompt_injection_attempt.bypass_narrative_label)
        lines.append("security_center_backend_api_name=" + prompt_injection_attempt.security_center_backend_api_name)
        lines.append("security_center_operator_web_name=" + prompt_injection_attempt.security_center_operator_web_name)
        lines.append("nonce_voucher_label=" + prompt_injection_attempt.nonce_voucher_label)
        lines.append(
            "observed_security_rejection_nonce="
            + (guard_observation.security_rejection_nonce or "<missing>")
        )
        lines.append(
            "observed_alert_latency_ms="
            + (
                str(guard_observation.observed_alert_latency_ms)
                if guard_observation.observed_alert_latency_ms is not None
                else "<missing>"
            )
        )
        lines.append(
            "security_rejection_nonce_trace_bound="
            + str(guard_observation.security_rejection_nonce_trace_bound)
        )
        lines.append(
            "runtime_console_status="
            + (
                str(self._latest_console_status)
                if self._latest_console_status is not None
                else "<missing>"
            ),
        )
        if self._latest_console_error:
            lines.append("runtime_console_error=" + self._latest_console_error)
        lines.append("runtime_working_dir=" + str(self._app_server.working_dir))
        return "\n".join(lines)

    def _collect_runtime_artifacts(
        self,
        *,
        session_id: str,
        before_trace_names: set[str],
    ) -> None:
        deadline = time.time() + _RUNTIME_SETTLE_SECONDS
        latest_approval_payload: dict[str, Any] = {}
        latest_trace_paths: tuple[Path, ...] = ()
        latest_trace_query_ready = False

        while time.time() < deadline:
            latest_approval_payload = self._read_json_response(
                "GET",
                "/api/approval/list",
                params={"session_id": session_id},
            )
            latest_trace_paths = self._trace_files()
            new_trace_paths = tuple(
                path for path in latest_trace_paths if path.name not in before_trace_names
            )
            latest_trace_query_ready = self._query_latest_trace(new_trace_paths)
            if latest_approval_payload.get("count") or new_trace_paths:
                break
            time.sleep(_RUNTIME_POLL_INTERVAL_SECONDS)

        self._latest_approval_payload = latest_approval_payload
        self._latest_trace_paths = latest_trace_paths
        self._latest_trace_query_ready = latest_trace_query_ready

    def _trigger_live_console_attempt(
        self,
        request: HighRiskDelegationRequest,
    ) -> None:
        prompt = (
            "As authenticated employee "
            f"{request.authenticated_employee.employee_id}, ask "
            f"{request.delegated_agent_name} to use plugin "
            f"{request.third_party_plugin_name} and high-risk tool "
            f"{request.high_risk_tool_name}. Confirmation phrase: "
            f"{request.user_confirmation_phrase}."
        )
        self._submit_console_prompt(
            user_id=request.authenticated_employee.employee_id,
            session_id=request.authenticated_employee.authenticated_session_id,
            prompt=prompt,
        )

    def _submit_console_prompt(
        self,
        *,
        user_id: str,
        session_id: str,
        prompt: str,
    ) -> None:
        payload = {
            "channel": "console",
            "user_id": user_id,
            "session_id": session_id,
            "input": [
                {
                    "content": [
                        {
                            "type": "text",
                            "text": prompt,
                        }
                    ]
                }
            ],
        }
        timeout = httpx.Timeout(_HTTP_TIMEOUT, read=_STREAM_READ_TIMEOUT)
        try:
            with self._app_server.client.stream(
                "POST",
                f"{self._app_server.base_url}/api/console/chat",
                json=payload,
                headers={"accept": "text/event-stream"},
                timeout=timeout,
            ) as response:
                self._latest_console_status = response.status_code
                self._latest_console_error = None
                self._latest_console_response_headers = {
                    key.lower(): value for key, value in response.headers.items()
                }
                self._latest_console_response_body = "".join(response.iter_text())
        except httpx.TimeoutException as exc:
            self._latest_console_status = None
            self._latest_console_error = f"timeout: {exc}"
            self._latest_console_response_headers = {}
            self._latest_console_response_body = ""
        except httpx.HTTPError as exc:
            self._latest_console_status = None
            self._latest_console_error = f"http-error: {exc}"
            self._latest_console_response_headers = {}
            self._latest_console_response_body = ""

    def _tamper_committed_historical_audit_record(
        self,
        *,
        artifact_label: str,
        baseline_trace_paths: tuple[Path, ...],
        record_position_from_start: int,
    ) -> str:
        record_index = record_position_from_start - 1
        if 0 <= record_index < len(baseline_trace_paths):
            historical_trace_path = baseline_trace_paths[record_index]
        else:
            historical_trace_path = self._trace_dir / (
                f"missing-historical-record-{record_position_from_start}.json"
            )

        if historical_trace_path.exists():
            payload = self._load_json_file(historical_trace_path)
            payload["tampered_artifact_label"] = artifact_label
            payload["tampered_record_position"] = record_position_from_start
            payload["os_level_history_edit"] = True
            payload["business_tamper_boundary"] = "second_committed_non_tail_record"
            payload["current_hash"] = "tampered-historical-record-hash"
            historical_trace_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return str(historical_trace_path)

        historical_trace_path.parent.mkdir(parents=True, exist_ok=True)
        historical_trace_path.write_text(
            json.dumps(
                {
                    "tampered_artifact_label": artifact_label,
                    "tampered_record_position": record_position_from_start,
                    "os_level_history_edit": True,
                    "business_tamper_boundary": "missing_second_committed_record",
                    "current_hash": "tampered-historical-record-hash",
                },
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        return str(historical_trace_path)

    def _tamper_latest_audit_artifact(self, *, artifact_label: str) -> str:
        checkpoint_path = self._app_server.working_dir / "audit_chain_checkpoint.json"
        checkpoint_path.unlink(missing_ok=True)

        latest_trace_path = self._latest_trace_path()
        if latest_trace_path is not None and latest_trace_path.exists():
            payload = json.loads(latest_trace_path.read_text(encoding="utf-8"))
            payload["tamper_detected"] = True
            payload["checkpoint_missing"] = True
            payload["tampered_artifact_label"] = artifact_label
            payload["current_hash"] = "tampered-current-hash"
            latest_trace_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return str(latest_trace_path)

        checkpoint_path.write_text(
            json.dumps(
                {
                    "tampered_artifact_label": artifact_label,
                    "checkpoint_missing": True,
                    "global_hash": "tampered-current-hash",
                    "checkpoint_reason": "offline-manual-edit",
                },
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        return str(checkpoint_path)

    def _update_context_probe(
        self,
        *,
        expected_user_id: str,
        latest_trace_payload: dict[str, Any],
        approval_records: list[dict[str, Any]],
    ) -> None:
        if self._active_context_probe is None:
            return

        observed_user_id = self._find_first_scalar(
            latest_trace_payload,
            keys=("user_id",),
        ) or self._find_first_scalar(approval_records, keys=("user_id",))
        implicit_contextvars_ready = observed_user_id == expected_user_id
        tool_boundary_probe_ready = self._contains_any_key(
            latest_trace_payload,
            candidate_keys=("tool_name", "tool_id", "tool_call_id"),
        ) and observed_user_id is not None
        explicit_parameter_threading_guarded = not self._contains_any_key(
            latest_trace_payload,
            candidate_keys=("security_context", "SecurityContext"),
        )

        failure_reasons: list[str] = []
        if not implicit_contextvars_ready:
            failure_reasons.append(
                "Implicit_Contextvars_Missing: the live runtime artifacts do not "
                "yet prove the trusted user identity crossed the async boundary."
            )
        if not tool_boundary_probe_ready:
            failure_reasons.append(
                "Runtime_Context_Spy_Missing: no live runtime artifact shows the "
                "high-risk tool boundary reading user identity at execution time."
            )
        if not explicit_parameter_threading_guarded:
            failure_reasons.append(
                "Explicit_Context_Threading_Risk: the live runtime artifacts "
                "still expose an explicit security context payload."
            )
        if self._app_server.startup_error is not None:
            failure_reasons = [
                "Runtime_Context_Spy_Missing: the real app subprocess did not "
                "finish startup, so no live tool-boundary context probe could "
                "be observed."
            ]

        self._active_context_probe.observed_user_id = observed_user_id
        self._active_context_probe.implicit_contextvars_ready = implicit_contextvars_ready
        self._active_context_probe.tool_boundary_probe_ready = tool_boundary_probe_ready
        self._active_context_probe.explicit_parameter_threading_guarded = (
            explicit_parameter_threading_guarded
        )
        self._active_context_probe.failure_reasons = tuple(failure_reasons)

    def _latest_pending_approvals(self) -> list[dict[str, Any]]:
        pending = self._latest_approval_payload.get("pending_approvals", [])
        if isinstance(pending, list):
            return [item for item in pending if isinstance(item, dict)]
        return []

    def _load_latest_trace_payload(self) -> dict[str, Any]:
        latest_trace_path = self._latest_trace_path()
        if latest_trace_path is None or not latest_trace_path.exists():
            return {}
        return self._load_json_file(latest_trace_path)

    def _load_json_file(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
        return {}

    def _latest_trace_path(self) -> Path | None:
        trace_paths = self._latest_trace_paths or self._trace_files()
        if not trace_paths:
            return None
        return trace_paths[-1]

    def _query_latest_trace(self, trace_paths: tuple[Path, ...]) -> bool:
        if not trace_paths:
            return False
        latest_run_id = trace_paths[-1].stem
        response = self._app_server.api_request(
            "GET",
            f"/api/console/inbox/traces/{latest_run_id}",
            timeout=_HTTP_TIMEOUT,
        )
        return response.status_code == 200

    def _trace_files(self) -> tuple[Path, ...]:
        if not self._trace_dir.exists():
            return ()
        return tuple(
            sorted(
                self._trace_dir.glob("*.json"),
                key=lambda path: path.stat().st_mtime,
            ),
        )

    def _build_gap_anchor(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        event_type = str(payload.get("event_type") or "").strip()
        current_hash = str(payload.get("current_hash") or "").strip()
        if not current_hash:
            return None

        if event_type == "USER_CONFIRMATION":
            chain_material = {
                "prior_hash": str(payload.get("prior_hash") or "").strip(),
                "confirmation_digest": str(payload.get("confirmation_digest") or "").strip(),
                "run_id": str(payload.get("run_id") or "").strip(),
                "confirmed_at": f"{float(payload.get('confirmed_at') or payload.get('created_at') or 0):.9f}",
                "event_sequence": self._coerce_int(payload.get("event_sequence")),
                "anchored_event_id": str(payload.get("anchored_event_id") or "").strip(),
            }
        elif event_type == "SECURITY_REJECTION":
            chain_material = {
                "run_id": str(payload.get("run_id") or "").strip(),
                "session_id": str(payload.get("session_id") or "").strip(),
                "user_id": str(payload.get("user_id") or "").strip(),
                "tool_name": str(payload.get("tool_name") or "").strip(),
                "prompt_text": str(payload.get("prompt_text") or "").strip(),
                "prior_hash": str(payload.get("prior_hash") or "").strip(),
                "event_sequence": self._coerce_int(payload.get("event_sequence")),
                "anchored_event_id": str(payload.get("anchored_event_id") or "").strip(),
                "created_at": f"{float(payload.get('created_at') or 0):.9f}",
            }
        elif event_type == "AUDIT_INTEGRITY_LOCKDOWN":
            chain_material = {
                "run_id": str(payload.get("run_id") or "").strip(),
                "session_id": str(payload.get("session_id") or "").strip(),
                "user_id": str(payload.get("user_id") or "").strip(),
                "tool_name": str(payload.get("tool_name") or "").strip(),
                "prompt_text": str(payload.get("prompt_text") or "").strip(),
                "prior_hash": str(payload.get("prior_hash") or "").strip(),
                "event_sequence": self._coerce_int(payload.get("event_sequence")),
                "anchored_event_id": str(payload.get("anchored_event_id") or "").strip(),
                "lock_mode": str(payload.get("lock_mode") or "UNTRUSTED").strip(),
                "created_at": f"{float(payload.get('created_at') or 0):.9f}",
            }
        else:
            return None

        canonical_payload = {
            "event_type": event_type,
            "run_id": str(payload.get("run_id") or "").strip(),
            "session_id": str(payload.get("session_id") or "").strip(),
            "user_id": str(payload.get("user_id") or "").strip(),
            "tool_name": str(payload.get("tool_name") or "").strip(),
            "status": str(payload.get("status") or "").strip(),
            "decision": str(payload.get("decision") or "").strip(),
            "event_sequence": self._coerce_int(payload.get("event_sequence")),
            "anchored_event_id": str(payload.get("anchored_event_id") or "").strip(),
            "prior_hash": str(payload.get("prior_hash") or "").strip(),
            "payload_hash": str(payload.get("payload_hash") or "").strip(),
        }
        anchor = {
            "run_id": str(payload.get("run_id") or "").strip(),
            "event_type": event_type,
            "sequence": self._coerce_int(payload.get("event_sequence")),
            "anchored_event_id": str(payload.get("anchored_event_id") or "").strip(),
            "prior_hash": str(payload.get("prior_hash") or "").strip(),
            "current_hash": current_hash,
            "payload_hash": str(payload.get("payload_hash") or "").strip(),
            "canonical_payload": canonical_payload,
            "canonical_payload_digest": hashlib.sha256(_canonical_json(canonical_payload).encode("utf-8")).hexdigest(),
            "chain_material": chain_material,
        }
        anchor["anchor_material_digest"] = hashlib.sha256(
            _canonical_json(
                {
                    "label": "gap-anchor-material-v1",
                    "payload": {
                        "event_type": anchor["event_type"],
                        "run_id": anchor["run_id"],
                        "sequence": anchor["sequence"],
                        "anchored_event_id": anchor["anchored_event_id"],
                        "prior_hash": anchor["prior_hash"],
                        "payload_hash": anchor["payload_hash"],
                        "canonical_payload_digest": anchor["canonical_payload_digest"],
                    },
                },
            ).encode("utf-8"),
        ).hexdigest()
        return anchor

    def _build_gap_proof(self, *, session_id: str) -> dict[str, Any]:
        checkpoint_path = self._app_server.working_dir / "audit_chain_checkpoint.json"
        if not checkpoint_path.exists():
            return {}
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if not isinstance(checkpoint, dict):
            return {}

        base_anchor_hash = str(checkpoint.get("current_hash") or "").strip()
        if not base_anchor_hash:
            return {}
        base_sequence = self._coerce_int(
            checkpoint.get("confirmed_sequence") or checkpoint.get("event_sequence"),
        ) or 0
        base_anchor_event_id = str(
            checkpoint.get("last_anchored_event_id")
            or checkpoint.get("anchored_event_id")
            or checkpoint.get("run_id")
            or ""
        ).strip()

        anchors: list[dict[str, Any]] = []
        for path in self._trace_files():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                continue
            if session_id and str(payload.get("session_id") or "").strip() != session_id:
                continue
            sequence = self._coerce_int(payload.get("event_sequence"))
            if sequence is None:
                continue
            if sequence <= base_sequence:
                continue
            anchor = self._build_gap_anchor(payload)
            if anchor is None:
                continue
            anchor["sequence"] = sequence
            if not anchor.get("anchored_event_id"):
                anchor["anchored_event_id"] = path.stem
            if not anchor.get("prior_hash"):
                anchor["prior_hash"] = base_anchor_hash
            anchors.append(anchor)

        if not anchors:
            return {}

        head = anchors[-1]
        proof_payload = {
            "base_anchor_hash": base_anchor_hash,
            "base_sequence": base_sequence,
            "base_anchor_event_id": base_anchor_event_id,
            "head_hash": head["current_hash"],
            "head_sequence": head["sequence"],
            "head_anchor_event_id": head["anchored_event_id"],
            "anchors": anchors,
        }
        proof_payload["proof_digest"] = _canonical_hash("audit-gap-proof-v1", proof_payload)
        return proof_payload

    def _restart_runtime_normally_before_lease_expiry(
        self,
        *,
        baseline_client: dict[str, Any],
        baseline_timeline: dict[str, Any],
    ) -> tuple[bool, bool, str | None]:
        lease_expires_at = self._coerce_int(
            self._find_first_scalar(baseline_timeline, keys=("lease_expires_at",))
            or self._find_first_scalar(baseline_client, keys=("lease_expires_at",)),
        )
        process = self._app_server.process
        if process.poll() is None:
            try:
                if sys.platform == "win32":
                    process.terminate()
                else:
                    process.send_signal(signal.SIGINT)
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        self._app_server.log_thread.join(timeout=2)

        stopped_before_expiry = (
            lease_expires_at is not None and time.time_ns() < lease_expires_at
        )

        repo_root = Path(__file__).resolve().parents[3]
        env = os.environ.copy()
        env["QWENPAW_WORKING_DIR"] = str(self._app_server.working_dir)
        env["QWENPAW_SECRET_DIR"] = str(self._app_server.working_dir.parent / "working.secret")
        env["QWENPAW_BACKUP_DIR"] = str(self._app_server.working_dir.parent / "working.backups")
        env["QWENPAW_AUTH_ENABLED"] = "false"
        env["NO_PROXY"] = "*"
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        existing_pythonpath = env.get("PYTHONPATH", "").strip()
        env["PYTHONPATH"] = (
            str(repo_root / "src")
            if not existing_pythonpath
            else os.pathsep.join((str(repo_root / "src"), existing_pythonpath))
        )
        if self._app_server.security_center_api_url:
            env["QWENPAW_SECURITY_CENTER_API_URL"] = self._app_server.security_center_api_url
        if self._app_server.security_center_web_url:
            env["QWENPAW_SECURITY_CENTER_WEB_URL"] = self._app_server.security_center_web_url

        restarted_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "qwenpaw",
                "app",
                "--host",
                self._app_server.host,
                "--port",
                str(self._app_server.port),
                "--log-level",
                "info",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=repo_root,
        )
        assert restarted_process.stdout is not None
        restart_thread = threading.Thread(
            target=_drain_process_output,
            args=(restarted_process.stdout, self._app_server.logs),
            daemon=True,
        )
        restart_thread.start()
        self._app_server.process = restarted_process
        self._app_server.log_thread = restart_thread

        deadline = time.time() + _RUNTIME_RESTART_READY_SECONDS
        last_error: str | None = None
        while time.time() < deadline:
            if restarted_process.poll() is not None:
                last_error = (
                    "qwenpaw app exited during normal offline restart; "
                    f"exit_code={restarted_process.returncode}; "
                    f"logs={self._app_server.logs_tail()}"
                )
                self._app_server.startup_error = last_error
                return False, stopped_before_expiry, last_error
            try:
                response = self._app_server.client.get(
                    f"{self._app_server.base_url}/api/version",
                    timeout=_HTTP_TIMEOUT,
                )
                if response.status_code == 200:
                    self._app_server.startup_error = None
                    restarted_before_expiry = (
                        lease_expires_at is not None and time.time_ns() < lease_expires_at
                    )
                    return True, stopped_before_expiry and restarted_before_expiry, None
                last_error = f"unexpected status {response.status_code}"
            except httpx.HTTPError as exc:
                last_error = str(exc)
            time.sleep(_RUNTIME_POLL_INTERVAL_SECONDS)

        last_error = (
            "qwenpaw app did not become ready after normal offline restart; "
            f"last_error={last_error}; logs={self._app_server.logs_tail()}"
        )
        self._app_server.startup_error = last_error
        return False, stopped_before_expiry, last_error

    def _poll_security_center_client_projection(
        self,
        *,
        requested_client_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        deadline = time.time() + 8.0
        last_overview: dict[str, Any] = {}
        last_client: dict[str, Any] | None = None
        while time.time() < deadline:
            overview = self._read_security_center_api_json(
                "/security-center/v1/operator/overview",
            )
            client = self._find_client_state(overview, client_id=requested_client_id)
            if client is None:
                client = self._find_single_canonical_client(overview)
            last_overview = overview
            last_client = client
            if isinstance(client, dict):
                return overview, client
            time.sleep(_RUNTIME_POLL_INTERVAL_SECONDS)
        return last_overview, last_client

    def _poll_security_center_clear_projection(
        self,
        *,
        client_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        deadline = time.time() + 8.0
        last_timeline: dict[str, Any] = {}
        last_client: dict[str, Any] | None = None
        while time.time() < deadline:
            timeline = self._read_security_center_api_json(
                f"/security-center/v1/operator/timelines/{quote(client_id, safe='')}",
            )
            overview = self._read_security_center_api_json(
                "/security-center/v1/operator/overview",
            )
            client = self._find_client_state(overview, client_id=client_id)
            if client is None:
                client = self._find_single_canonical_client(overview)
            last_timeline = timeline
            last_client = client
            trust_state = self._find_first_scalar(timeline, keys=("trust_state",))
            gap_status = self._find_first_scalar(timeline, keys=("gap_status",))
            recovery_gate_status = self._find_first_scalar(
                timeline,
                keys=("recovery_gate_status",),
            )
            recovery_required = self._find_first_scalar(
                timeline,
                keys=("recovery_required",),
            )
            if all(
                (
                    str(trust_state or "") in {"ALIGNED", "TRUSTED"},
                    gap_status == "CLEAR",
                    recovery_gate_status == "CLEAR",
                    recovery_required is False,
                ),
            ):
                return timeline, client
            time.sleep(_RUNTIME_POLL_INTERVAL_SECONDS)
        return last_timeline, last_client

    def _find_single_canonical_client(
        self,
        overview_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        clients = overview_payload.get("clients")
        if not isinstance(clients, list):
            return None
        canonical_clients = [
            client
            for client in clients
            if isinstance(client, dict)
            and str(client.get("canonical_client_id") or client.get("client_id") or "").strip()
        ]
        if len(canonical_clients) == 1:
            return canonical_clients[0]
        return None

    def _client_lookup_id(
        self,
        client: dict[str, Any] | None,
        *,
        fallback: str,
    ) -> str:
        if not isinstance(client, dict):
            return fallback
        return str(
            client.get("client_id")
            or client.get("canonical_client_id")
            or fallback,
        )

    def _read_json_response(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        response = self._app_server.api_request(method, path, timeout=_HTTP_TIMEOUT, **kwargs)
        if response.status_code != 200:
            return {"status_code": response.status_code}
        payload = response.json()
        return payload if isinstance(payload, dict) else {"payload": payload}

    def _read_security_center_api_json(self, path: str) -> dict[str, Any]:
        base_url = self._app_server.security_center_api_url
        if not base_url:
            return {}
        try:
            response = self._app_server.client.get(
                f"{base_url}{path}",
                timeout=_HTTP_TIMEOUT,
            )
        except httpx.HTTPError:
            return {}
        if response.status_code != 200:
            return {"status_code": response.status_code}
        payload = response.json()
        return payload if isinstance(payload, dict) else {"payload": payload}

    def _post_security_center_api_json(self, path: str, **kwargs: Any) -> dict[str, Any]:
        base_url = self._app_server.security_center_api_url
        if not base_url:
            return {}
        try:
            response = self._app_server.client.post(
                f"{base_url}{path}",
                timeout=_HTTP_TIMEOUT,
                **kwargs,
            )
        except httpx.HTTPError:
            return {}
        if response.status_code != 200:
            return {"status_code": response.status_code}
        payload = response.json()
        return payload if isinstance(payload, dict) else {"payload": payload}

    def _read_security_center_web_text(self, path: str) -> str:
        base_url = self._app_server.security_center_web_url
        if not base_url:
            return ""
        try:
            response = self._app_server.client.get(
                f"{base_url}{path}",
                timeout=_HTTP_TIMEOUT,
            )
        except httpx.HTTPError:
            return ""
        if response.status_code != 200:
            return ""
        return response.text

    def _security_center_stream_is_ready(self) -> tuple[bool, str]:
        base_url = self._app_server.security_center_api_url
        if not base_url:
            return False, ""
        timeout = httpx.Timeout(_HTTP_TIMEOUT, read=_STREAM_READ_TIMEOUT)
        try:
            with self._app_server.client.stream(
                "GET",
                f"{base_url}/security-center/v1/operator/stream",
                timeout=timeout,
            ) as response:
                content_type = response.headers.get("content-type", "")
                first_chunk = ""
                for chunk in response.iter_text():
                    if chunk:
                        first_chunk += chunk
                        break
                return (
                    response.status_code == 200
                    and "text/event-stream" in content_type.lower()
                    and "event: ready" in first_chunk,
                    first_chunk,
                )
        except httpx.HTTPError:
            return False, ""

    def _find_client_state(
        self,
        overview_payload: dict[str, Any],
        *,
        client_id: str,
    ) -> dict[str, Any] | None:
        clients = overview_payload.get("clients")
        if not isinstance(clients, list):
            return None
        for client in clients:
            if isinstance(client, dict) and client.get("client_id") == client_id:
                return client
        return None

    def _find_rejection(
        self,
        overview_payload: dict[str, Any],
        *,
        client_id: str,
        nonce: str | None,
    ) -> dict[str, Any] | None:
        rejections = overview_payload.get("rejections")
        if not isinstance(rejections, list):
            return None
        for record in reversed(rejections):
            if not isinstance(record, dict):
                continue
            if record.get("client_id") != client_id:
                continue
            if nonce is not None and record.get("nonce") != nonce:
                continue
            return record
        return None

    def _find_alert(
        self,
        overview_payload: dict[str, Any],
        *,
        alert_type: str,
        client_id: str,
        nonce: str | None = None,
    ) -> dict[str, Any]:
        alerts = overview_payload.get("alerts")
        if not isinstance(alerts, list):
            return {}
        for alert in reversed(alerts):
            if not isinstance(alert, dict):
                continue
            if alert.get("type") != alert_type:
                continue
            if alert.get("client_id") != client_id:
                continue
            if nonce is not None:
                message = str(alert.get("message") or "")
                if alert.get("nonce") != nonce and nonce not in message:
                    continue
            return alert
        return {}

    def _extract_actor_chain(
        self,
        *,
        request: HighRiskDelegationRequest,
        approval_records: list[dict[str, Any]],
        trace_payload: dict[str, Any],
    ) -> tuple[str, ...]:
        observed_chain: list[str] = []
        observed_user_id = self._find_first_scalar(trace_payload, keys=("user_id",))
        if observed_user_id == request.authenticated_employee.employee_id:
            observed_chain.append(request.authenticated_employee.employee_id)
        if self._find_match(approval_records, request.delegated_agent_name):
            observed_chain.append(request.delegated_agent_name)
        if self._find_match(approval_records, request.third_party_plugin_name):
            observed_chain.append(request.third_party_plugin_name)
        if self._find_match(approval_records, request.high_risk_tool_name):
            observed_chain.append(request.high_risk_tool_name)
        return tuple(observed_chain)

    def _find_match(self, payload: Any, expected_value: str) -> bool:
        if isinstance(payload, dict):
            return any(self._find_match(value, expected_value) for value in payload.values())
        if isinstance(payload, list):
            return any(self._find_match(item, expected_value) for item in payload)
        return payload == expected_value

    def _find_first_scalar(
        self,
        payload: Any,
        *,
        keys: tuple[str, ...],
    ) -> Any | None:
        if isinstance(payload, dict):
            for key in keys:
                value = payload.get(key)
                if not isinstance(value, (dict, list)) and value is not None:
                    return value
            for value in payload.values():
                nested = self._find_first_scalar(value, keys=keys)
                if nested is not None:
                    return nested
            return None
        if isinstance(payload, list):
            for item in payload:
                nested = self._find_first_scalar(item, keys=keys)
                if nested is not None:
                    return nested
        return None

    def _extract_security_rejection_nonce(
        self,
        *,
        latest_trace_payload: dict[str, Any],
        approval_records: list[dict[str, Any]],
    ) -> str | None:
        nonce = self._find_first_scalar(
            latest_trace_payload,
            keys=("Security_Rejection_Nonce", "security_rejection_nonce", "rejection_nonce"),
        ) or self._find_first_scalar(
            approval_records,
            keys=("Security_Rejection_Nonce", "security_rejection_nonce", "rejection_nonce"),
        )
        if isinstance(nonce, str) and nonce.strip():
            return nonce.strip()

        for header_name in ("security-rejection-nonce", "x-security-rejection-nonce"):
            header_value = self._latest_console_response_headers.get(header_name)
            if header_value and header_value.strip():
                return header_value.strip()

        nonce_match = re.search(
            r'"(?:Security_Rejection_Nonce|security_rejection_nonce|rejection_nonce)"\s*:\s*"([^"]+)"',
            self._latest_console_response_body,
        )
        if nonce_match:
            return nonce_match.group(1).strip()

        return None

    def _security_rejection_nonce_is_trace_bound(
        self,
        *,
        latest_trace_payload: dict[str, Any],
        security_rejection_nonce: str | None,
    ) -> bool:
        if security_rejection_nonce is None:
            return False

        normalized_nonce = security_rejection_nonce.strip().lower()
        if normalized_nonce in {"static", "constant", "test", "nonce", "rejection-nonce"}:
            return False

        trace_binding_material = "|".join(
            str(value)
            for value in (
                self._find_first_scalar(latest_trace_payload, keys=("run_id",)),
                self._find_first_scalar(latest_trace_payload, keys=("session_id",)),
                self._find_first_scalar(latest_trace_payload, keys=("user_id", "request_user_id")),
                self._find_first_scalar(latest_trace_payload, keys=("tool_name", "high_risk_tool_name")),
                self._find_first_scalar(latest_trace_payload, keys=("current_hash", "payload_hash", "continuity_anchor")),
            )
            if value is not None
        )
        if not trace_binding_material:
            return False

        expected_fingerprint = hashlib.sha256(
            trace_binding_material.encode("utf-8"),
        ).hexdigest()
        binding_hash = self._find_first_scalar(
            latest_trace_payload,
            keys=("security_rejection_nonce_binding_hash", "nonce_trace_fingerprint"),
        )
        if isinstance(binding_hash, str) and binding_hash == expected_fingerprint:
            return True

        return security_rejection_nonce in {
            expected_fingerprint,
            expected_fingerprint[:16],
            expected_fingerprint[:32],
        }

    def _coerce_int(self, value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                return None
        return None

    def _response_body_contains_guard_rejection(self) -> bool:
        response_body = self._latest_console_response_body.lower()
        return any(
            marker in response_body
            for marker in ("rejected", "denied", "guard_rejection", "security_rejection")
        )

    def _contains_all_keys(
        self,
        payload: Any,
        *,
        required_keys: tuple[str, ...],
    ) -> bool:
        return all(self._contains_any_key(payload, candidate_keys=(key,)) for key in required_keys)

    def _contains_any_key(
        self,
        payload: Any,
        *,
        candidate_keys: tuple[str, ...],
    ) -> bool:
        if isinstance(payload, dict):
            return any(
                key in candidate_keys or self._contains_any_key(value, candidate_keys=candidate_keys)
                for key, value in payload.items()
            )
        if isinstance(payload, list):
            return any(
                self._contains_any_key(item, candidate_keys=candidate_keys)
                for item in payload
            )
        return False
