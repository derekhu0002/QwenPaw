from __future__ import annotations

import hashlib
import json
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from tests.integration.conftest import AppServer

_HTTP_TIMEOUT = 45.0
_STREAM_READ_TIMEOUT = 5.0
_RUNTIME_SETTLE_SECONDS = 5.0
_RUNTIME_POLL_INTERVAL_SECONDS = 0.25


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
    sensitive_tool_name: str
    tampered_artifact_label: str
    reconnect_action_label: str
    security_center_backend_api_name: str
    security_center_operator_web_name: str
    hash_break_curve_chart_name: str


@dataclass(frozen=True)
class AuditIntegrityLockdownObservation:
    tampered_artifact_path: str
    continuity_anomaly_ready: bool
    checkpoint_loss_treated_as_tamper: bool
    local_lock_mode_ready: bool
    sensitive_tool_blocked: bool
    backend_api_projection_ready: bool
    operator_web_projection_ready: bool
    hash_break_curve_chart_ready: bool
    hash_break_fork_point_ready: bool
    cloud_recovery_projection_ready: bool
    recovery_handshake_ready: bool
    failure_reasons: tuple[str, ...]

    def enforces_lockdown(self) -> bool:
        return all(
            (
                self.continuity_anomaly_ready,
                self.checkpoint_loss_treated_as_tamper,
                self.local_lock_mode_ready,
                self.sensitive_tool_blocked,
                self.backend_api_projection_ready,
                self.operator_web_projection_ready,
                self.hash_break_curve_chart_ready,
                self.hash_break_fork_point_ready,
                self.cloud_recovery_projection_ready,
                self.recovery_handshake_ready,
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
                continuity_anomaly_ready=False,
                checkpoint_loss_treated_as_tamper=False,
                local_lock_mode_ready=False,
                sensitive_tool_blocked=False,
                backend_api_projection_ready=False,
                operator_web_projection_ready=False,
                hash_break_curve_chart_ready=False,
                hash_break_fork_point_ready=False,
                cloud_recovery_projection_ready=False,
                recovery_handshake_ready=False,
                failure_reasons=(
                    "Real_Runtime_Bootstrap_Blocking_Dependency: the real app "
                    "subprocess could not finish startup, so sec-e2e-025 could "
                    "not drive a live tamper-and-resume flow.",
                ),
            )

        baseline_request = HighRiskDelegationRequest(
            authenticated_employee=request.authenticated_employee,
            delegated_agent_name="security_audit_agent",
            third_party_plugin_name=request.security_center_backend_api_name,
            high_risk_tool_name=request.sensitive_tool_name,
            user_confirmation_phrase="Approve audit integrity baseline capture",
        )
        before_trace_names = {path.name for path in self._trace_files()}
        self._trigger_live_console_attempt(baseline_request)
        self._collect_runtime_artifacts(
            session_id=request.authenticated_employee.authenticated_session_id,
            before_trace_names=before_trace_names,
        )

        tampered_artifact_path = self._tamper_latest_audit_artifact(
            artifact_label=request.tampered_artifact_label,
        )
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
        checkpoint_path = self._app_server.working_dir / "audit_chain_checkpoint.json"
        checkpoint_missing_detected = not checkpoint_path.exists()
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
        checkpoint_loss_treated_as_tamper = checkpoint_missing_detected and (
            continuity_anomaly_ready or self._contains_any_key(
                latest_trace_payload,
                candidate_keys=("checkpoint_missing", "checkpoint_loss_detected"),
            )
        )
        local_lock_mode_ready = trust_state == "UNTRUSTED"
        sensitive_tool_blocked = self._latest_console_status in {401, 403, 409, 423}
        backend_api_projection_ready = self._contains_any_key(
            latest_trace_payload,
            candidate_keys=(
                "cloud_mirror_status",
                "uplink_status",
                "mirror_alert",
                "recovery_projection",
                "security_center_backend_api",
            ),
        ) or self._find_match(latest_trace_payload, request.security_center_backend_api_name)
        operator_web_projection_ready = self._contains_any_key(
            latest_trace_payload,
            candidate_keys=(
                "operator_dashboard_status",
                "operator_web_projection",
                "web_alert_state",
                "security_center_operator_web",
            ),
        ) or self._find_match(latest_trace_payload, request.security_center_operator_web_name)
        hash_break_curve_chart_ready = self._contains_any_key(
            latest_trace_payload,
            candidate_keys=(
                "hash_break_curve_chart",
                "hash_divergence_curve",
                "shadow_hash_curve",
                "continuity_curve_series",
            ),
        ) or self._find_match(latest_trace_payload, request.hash_break_curve_chart_name)
        hash_break_fork_point_ready = self._contains_any_key(
            latest_trace_payload,
            candidate_keys=(
                "fork_point_hash",
                "fork_point_event_id",
                "hash_divergence_fork_point",
                "fork_sequence_number",
            ),
        )
        cloud_recovery_projection_ready = self._contains_any_key(
            latest_trace_payload,
            candidate_keys=(
                "cloud_mirror_status",
                "uplink_status",
                "mirror_alert",
                "recovery_projection",
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
        if not recovery_handshake_ready:
            failure_reasons.append(
                "Recovery_Handshake_Missing: the live runtime does not yet "
                "prove a first-ask-then-upload recovery handshake before resume."
            )

        return AuditIntegrityLockdownObservation(
            tampered_artifact_path=tampered_artifact_path,
            continuity_anomaly_ready=continuity_anomaly_ready,
            checkpoint_loss_treated_as_tamper=checkpoint_loss_treated_as_tamper,
            local_lock_mode_ready=local_lock_mode_ready,
            sensitive_tool_blocked=sensitive_tool_blocked,
            backend_api_projection_ready=backend_api_projection_ready,
            operator_web_projection_ready=operator_web_projection_ready,
            hash_break_curve_chart_ready=hash_break_curve_chart_ready,
            hash_break_fork_point_ready=hash_break_fork_point_ready,
            cloud_recovery_projection_ready=cloud_recovery_projection_ready,
            recovery_handshake_ready=recovery_handshake_ready,
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
        security_rejection_nonce = self._extract_security_rejection_nonce(
            latest_trace_payload=latest_trace_payload,
            approval_records=approval_records,
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
        backend_api_rejection_ready = self._contains_any_key(
            latest_trace_payload,
            candidate_keys=(
                "security_center_backend_api",
                "backend_api_rejection_status",
                "rejected_event_api_status",
                "operator_query_api_status",
            ),
        ) or self._find_match(latest_trace_payload, attempt.security_center_backend_api_name)
        operator_web_rejection_ready = self._contains_any_key(
            latest_trace_payload,
            candidate_keys=(
                "security_center_operator_web",
                "operator_web_projection",
                "operator_dashboard_status",
                "web_rejection_state",
            ),
        ) or self._find_match(latest_trace_payload, attempt.security_center_operator_web_name)
        nonce_voucher_ready = (
            security_rejection_nonce is not None and (
                self._contains_any_key(
                    latest_trace_payload,
                    candidate_keys=(
                        "nonce_voucher",
                        "security_rejection_voucher",
                        "voucher_nonce",
                    ),
                )
                or self._find_match(latest_trace_payload, attempt.nonce_voucher_label)
            )
        )
        realtime_push_channel_ready = self._contains_any_key(
            latest_trace_payload,
            candidate_keys=(
                "sse_stream",
                "websocket_channel",
                "realtime_push_channel",
                "operator_alert_stream",
            ),
        ) or any(
            marker in self._latest_console_response_body.lower()
            for marker in ("text/event-stream", "websocket", "server-sent events")
        )
        observed_alert_latency_ms = self._coerce_int(
            self._find_first_scalar(
                latest_trace_payload,
                keys=(
                    "alert_latency_ms",
                    "web_alert_latency_ms",
                    "realtime_alert_latency_ms",
                    "operator_alert_latency_ms",
                ),
            ),
        )
        realtime_red_alert_ready = (
            realtime_push_channel_ready
            and observed_alert_latency_ms is not None
            and observed_alert_latency_ms < 500
            and self._contains_any_key(
                latest_trace_payload,
                candidate_keys=(
                    "red_alert_state",
                    "rejection_alert_state",
                    "alert_severity",
                    "operator_popup_state",
                ),
            )
        )
        security_center_mirror_ready = self._contains_any_key(
            latest_trace_payload,
            candidate_keys=(
                "cloud_mirror_status",
                "uplink_status",
                "mirror_rejection_id",
                "rejected_sync_status",
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
        return json.loads(latest_trace_path.read_text(encoding="utf-8"))

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
            for key, value in payload.items():
                if key in keys and not isinstance(value, (dict, list)):
                    return value
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
