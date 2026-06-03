# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from .harness import (
    EmployeeIdentity,
    HighRiskDelegationRequest,
    SecurityAuditHarness,
)


@pytest.mark.integration
@pytest.mark.p0
def test_end_to_end_non_repudiation_evidence_chain() -> None:
    """Control point: authenticated employee requests a delegated high-risk action
    and confirms it.

    Observation point: the resulting evidence chain must remain continuous from
    employee to agent to plugin to tool, and it must be bound to a durable
    confirmation artifact digest that a Security Center style query seam can
    expose to operators.
    """

    harness = SecurityAuditHarness.for_repo_root()

    # // GIVEN
    authenticated_employee = EmployeeIdentity(
        employee_id="employee_a",
        channel_name="local_console",
        authenticated_session_id="session_employee_a",
    )
    confirmed_high_risk_operation = HighRiskDelegationRequest(
        authenticated_employee=authenticated_employee,
        delegated_agent_name="agent_b",
        third_party_plugin_name="plugin_c",
        high_risk_tool_name="tool_d",
        user_confirmation_phrase="Approve payroll export for finance closing",
    )

    # // WHEN
    with harness.expect_context_propagation(
        expected_user_id=authenticated_employee.employee_id,
    ) as context_propagation_at_tool_boundary:
        observed_evidence_chain = (
            harness.execute_high_risk_delegation_with_confirmation(
                confirmed_high_risk_operation,
            )
        )

    # // THEN
    last_audit_record = harness.get_last_audit_record_from_disk()
    local_hash_chain_integrity = harness.verify_local_hash_chain_integrity()
    pre_execution_evidence_order = (
        harness.verify_confirmation_precedes_high_risk_tool_effect(
            confirmed_high_risk_operation,
        )
    )

    assert (
        context_propagation_at_tool_boundary.is_trusted()
        and observed_evidence_chain.is_contract_ready()
        and last_audit_record.matches_confirmation_artifact(
            confirmed_high_risk_operation.digest(),
        )
        and local_hash_chain_integrity.is_intact()
        and pre_execution_evidence_order.is_pre_execution()
    ), harness.render_non_repudiation_failure_report(
        context_propagation_at_tool_boundary=context_propagation_at_tool_boundary,
        observed_evidence_chain=observed_evidence_chain,
        last_audit_record=last_audit_record,
        local_hash_chain_integrity=local_hash_chain_integrity,
        pre_execution_evidence_order=pre_execution_evidence_order,
        expected_confirmation_digest=confirmed_high_risk_operation.digest(),
    )
