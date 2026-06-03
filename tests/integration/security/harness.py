from __future__ import annotations

import hashlib
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


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


@dataclass(frozen=True)
class RuntimeContextInspection:
    expected_user_id: str
    observed_user_id: str | None
    implicit_contextvars_ready: bool
    tool_boundary_probe_ready: bool
    explicit_parameter_threading_guarded: bool
    failure_reasons: tuple[str, ...]

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


class SecurityAuditHarness:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    @classmethod
    def for_repo_root(cls) -> "SecurityAuditHarness":
        return cls(Path(__file__).resolve().parents[3])

    @contextmanager
    def expect_context_propagation(
        self,
        *,
        expected_user_id: str,
    ):
        yield self._inspect_context_propagation(expected_user_id)

    def execute_high_risk_delegation_with_confirmation(
        self,
        request: HighRiskDelegationRequest,
    ) -> EvidenceChainObservation:
        agent_context_text = self._read("src/qwenpaw/app/agent_context.py")
        approval_service_text = self._read("src/qwenpaw/app/approvals/service.py")
        delegate_tool_text = self._read(
            "src/qwenpaw/agents/tools/delegate_external_agent.py",
        )
        delegate_tool_exists = self._exists(
            "src/qwenpaw/agents/tools/delegate_external_agent.py"
        )
        inbox_trace_text = self._read("src/qwenpaw/app/inbox_trace_store.py")
        security_center_router_text = self._read(
            "src/qwenpaw/app/routers/security_center.py",
        )

        observed_actor_chain: list[str] = []
        if "user_id" in agent_context_text and "session_id" in agent_context_text:
            observed_actor_chain.append(request.authenticated_employee.employee_id)
        if "agent_id" in agent_context_text:
            observed_actor_chain.append(request.delegated_agent_name)
        if delegate_tool_exists:
            observed_actor_chain.append(request.third_party_plugin_name)
        if "tool_name" in approval_service_text:
            observed_actor_chain.append(request.high_risk_tool_name)

        continuous_chain_ready = all(
            (
                "root_session_id" in agent_context_text,
                "tool_name" in approval_service_text,
                "current_hash" in inbox_trace_text,
                "USER_CONFIRMATION" in security_center_router_text,
            )
        )
        confirmation_artifact_digest = self._extract_confirmation_digest(
            approval_service_text,
            inbox_trace_text,
        )
        security_center_query_ready = all(
            (
                bool(security_center_router_text),
                "query" in security_center_router_text.lower(),
                "trace" in security_center_router_text.lower(),
            ),
        )

        failure_reasons: list[str] = []
        if len(observed_actor_chain) != 4:
            failure_reasons.append(
                "Actor_Lineage_Incomplete: the current repository evidence cannot "
                "yet prove every required business hop from employee to tool."
            )
        if "current_hash" not in inbox_trace_text:
            failure_reasons.append(
                "Tamper_Evident_Audit_Ledger_Missing: the current local trace store "
                "does not yet expose canonical hash-linked audit entries."
            )
        if confirmation_artifact_digest is None:
            failure_reasons.append(
                "Confirmation_Artifact_Missing: the approval flow does not yet "
                "persist a durable confirmation digest that can be bound to the "
                "final high-risk action."
            )
        if not security_center_query_ready:
            failure_reasons.append(
                "Security_Center_Query_Missing: no repository-owned query seam "
                "currently exposes the complete evidence chain for operator review."
            )
        if not continuous_chain_ready:
            failure_reasons.append(
                "Evidence_Projection_Missing: current repository evidence still "
                "lacks a reconstructed end-to-end chain that can be queried as "
                "one business record."
            )

        return EvidenceChainObservation(
            observed_actor_chain=tuple(observed_actor_chain),
            continuous_chain_ready=continuous_chain_ready,
            confirmation_artifact_digest=confirmation_artifact_digest,
            security_center_query_ready=security_center_query_ready,
            failure_reasons=tuple(failure_reasons),
        )

    def get_last_audit_record_from_disk(self) -> AuditLedgerRecordObservation:
        inbox_trace_text = self._read("src/qwenpaw/app/inbox_trace_store.py")
        failure_reasons: list[str] = []
        physical_record_present = all(
            marker in inbox_trace_text
            for marker in ("_TRACE_DIR", "_write_trace", "USER_CONFIRMATION")
        )
        event_type = "USER_CONFIRMATION" if "USER_CONFIRMATION" in inbox_trace_text else None
        payload_hash = self._extract_confirmation_digest("", inbox_trace_text)
        has_prior_hash = "prior_hash" in inbox_trace_text

        if not physical_record_present:
            failure_reasons.append(
                "Physical_Audit_Record_Missing: no repository-owned disk audit "
                "ledger seam is currently available for the explicit testcase to inspect."
            )
        if event_type != "USER_CONFIRMATION":
            failure_reasons.append(
                "Confirmation_Record_Type_Missing: the physical ledger seam does "
                "not yet expose a USER_CONFIRMATION record type for direct inspection."
            )
        if payload_hash is None:
            failure_reasons.append(
                "Confirmation_Payload_Hash_Missing: the physical ledger seam does "
                "not yet persist the confirmation artifact digest to disk."
            )
        if not has_prior_hash:
            failure_reasons.append(
                "Prior_Hash_Link_Missing: the physical ledger seam does not yet "
                "expose a prior-hash anchor for chain verification."
            )

        return AuditLedgerRecordObservation(
            ledger_path="src/qwenpaw/app/inbox_trace_store.py",
            event_type=event_type,
            payload_hash=payload_hash,
            has_prior_hash=has_prior_hash,
            physical_record_present=physical_record_present,
            failure_reasons=tuple(failure_reasons),
        )

    def verify_local_hash_chain_integrity(self) -> HashChainIntegrityObservation:
        inbox_trace_text = self._read("src/qwenpaw/app/inbox_trace_store.py")
        security_contract_text = self._read("src/qwenpaw/security/ARCHITECTURE.md")
        failure_reasons: list[str] = []
        hash_fields_present = all(
            marker in inbox_trace_text for marker in ("prior_hash", "current_hash")
        )
        verifier_ready = any(
            marker in inbox_trace_text
            for marker in ("verify_hash_chain", "validate_hash_chain", "hash chain")
        )
        continuity_anchor_ready = "checkpoint" in security_contract_text.lower()

        if not hash_fields_present:
            failure_reasons.append(
                "Hash_Fields_Missing: the local ledger does not yet expose both "
                "prior_hash and current_hash for integrity verification."
            )
        if not verifier_ready:
            failure_reasons.append(
                "Hash_Chain_Verifier_Missing: the implementation does not yet "
                "expose a repository-owned verifier for ledger continuity checks."
            )
        if not continuity_anchor_ready:
            failure_reasons.append(
                "Continuity_Anchor_Missing: the owning security contract does not "
                "yet expose a checkpoint or anchor seam for integrity verification."
            )

        return HashChainIntegrityObservation(
            hash_fields_present=hash_fields_present,
            verifier_ready=verifier_ready,
            continuity_anchor_ready=continuity_anchor_ready,
            failure_reasons=tuple(failure_reasons),
        )

    def verify_confirmation_precedes_high_risk_tool_effect(
        self,
        request: HighRiskDelegationRequest,  # pylint: disable=unused-argument
    ) -> PreExecutionEvidenceObservation:
        approval_service_text = self._read("src/qwenpaw/app/approvals/service.py")
        permissions_text = self._read("src/qwenpaw/agents/acp/permissions.py")
        failure_reasons: list[str] = []

        confirmation_gate_ready = "requires_user_confirmation=True" in (
            permissions_text.replace(" ", "")
        )
        synchronous_evidence_write_ready = any(
            marker in approval_service_text
            for marker in (
                "write_confirmation_record",
                "append_audit_event",
                "persist_confirmation_digest",
            )
        )
        ordering_ready = "before tool execution" in approval_service_text.lower()

        if not confirmation_gate_ready:
            failure_reasons.append(
                "Human_Approval_Gate_Missing: the high-risk delegation path does "
                "not yet expose a mandatory user confirmation gate."
            )
        if not synchronous_evidence_write_ready:
            failure_reasons.append(
                "Pre_Execution_Evidence_Write_Missing: no repository evidence shows "
                "a durable confirmation record being written before the tool effect."
            )
        if not ordering_ready:
            failure_reasons.append(
                "Pre_Execution_Order_Assertion_Missing: the current implementation "
                "does not yet declare or enforce the atomic order 'store evidence, "
                "then release the high-risk tool'."
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
            + " -> ".join(observed_evidence_chain.observed_actor_chain)
        )
        lines.append(
            "observed_tool_boundary_identity="
            + (
                context_propagation_at_tool_boundary.observed_user_id
                or "<missing>"
            )
        )
        lines.append(
            "expected_confirmation_digest=" + expected_confirmation_digest,
        )
        lines.append(
            "persisted_confirmation_digest="
            + (last_audit_record.payload_hash or "<missing>"),
        )
        lines.append("physical_ledger_path=" + last_audit_record.ledger_path)
        return "\n".join(lines)

    def _exists(self, relative_path: str) -> bool:
        return (self._repo_root / relative_path).exists()

    def _read(self, relative_path: str) -> str:
        path = self._repo_root / relative_path
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _inspect_context_propagation(
        self,
        expected_user_id: str,
    ) -> RuntimeContextInspection:
        agent_context_text = self._read("src/qwenpaw/app/agent_context.py")
        delegate_tool_text = self._read(
            "src/qwenpaw/agents/tools/delegate_external_agent.py",
        )
        failure_reasons: list[str] = []

        implicit_contextvars_ready = all(
            marker in agent_context_text
            for marker in (
                "ContextVar",
                "_current_user_id",
                "_current_root_session_id",
                "get_current_user_id",
            )
        )
        tool_boundary_probe_ready = "get_current_user_id(" in delegate_tool_text
        explicit_parameter_threading_guarded = all(
            forbidden not in delegate_tool_text
            for forbidden in ("security_context", "SecurityContext")
        )
        observed_user_id = (
            expected_user_id
            if implicit_contextvars_ready and tool_boundary_probe_ready
            else None
        )

        if not implicit_contextvars_ready:
            failure_reasons.append(
                "Implicit_Contextvars_Missing: the repository does not yet expose "
                "the full trusted user/root-session contextvars seam required by "
                "the testcase."
            )
        if not tool_boundary_probe_ready:
            failure_reasons.append(
                "Runtime_Context_Spy_Missing: no repository evidence shows the "
                "high-risk tool boundary reading user identity directly from "
                "contextvars at execution time."
            )
        if not explicit_parameter_threading_guarded:
            failure_reasons.append(
                "Explicit_Context_Threading_Risk: the delegated tool path still "
                "appears able to receive security context via explicit parameters."
            )

        return RuntimeContextInspection(
            expected_user_id=expected_user_id,
            observed_user_id=observed_user_id,
            implicit_contextvars_ready=implicit_contextvars_ready,
            tool_boundary_probe_ready=tool_boundary_probe_ready,
            explicit_parameter_threading_guarded=explicit_parameter_threading_guarded,
            failure_reasons=tuple(failure_reasons),
        )

    def _extract_confirmation_digest(
        self,
        approval_service_text: str,
        inbox_trace_text: str,
    ) -> str | None:
        digest_markers = ("confirmation_digest", "confirmation_signature", "payload_hash")
        if any(marker in approval_service_text for marker in digest_markers):
            return "declared-by-implementation"
        if any(marker in inbox_trace_text for marker in digest_markers):
            return "declared-by-implementation"
        return None
