const assert = require('assert');
const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..', '..');
const frozenExplicitTestcases = [
    {
        testcaseName: 'sec-e2e-024-end-to-end-non-repudiation-evidence-chain',
        entryPath: 'tests/integration/security/test_audit_foundation.py::test_end_to_end_non_repudiation_evidence_chain',
        requiredTestMarker: 'def test_end_to_end_non_repudiation_evidence_chain',
    },
    {
        testcaseName: 'sec-e2e-025-audit-integrity-self-healing-lockdown',
        entryPath: 'tests/integration/security/test_audit_foundation.py::test_audit_integrity_self_healing_lockdown',
        requiredTestMarker: 'def test_audit_integrity_self_healing_lockdown',
    },
    {
        testcaseName: 'sec-e2e-021-prompt-injection-tool-guard-enforced',
        entryPath: 'tests/integration/security/test_audit_foundation.py::test_prompt_injection_cannot_bypass_high_risk_tool_guard',
        requiredTestMarker: 'def test_prompt_injection_cannot_bypass_high_risk_tool_guard',
    },
    {
        testcaseName: 'sec-e2e-027-lease-expiry-active-defense',
        entryPath: 'tests/integration/security/test_audit_foundation.py::test_lease_expiry_blocks_untrusted_rejoin_until_gap_sync',
        requiredTestMarker: 'def test_lease_expiry_blocks_untrusted_rejoin_until_gap_sync',
    },
    {
        testcaseName: 'sec-e2e-028-normal-offline-reconnect-clear-state',
        entryPath: 'tests/integration/security/test_audit_foundation.py::test_normal_offline_reconnect_clears_without_gap_recovery',
        requiredTestMarker: 'def test_normal_offline_reconnect_clears_without_gap_recovery',
    },
    {
        testcaseName: 'sec-e2e-029-builtin-rule-line-ending-invariant',
        entryPath: 'extension/run-integrity-delivery-selftest.py',
        requiredTestMarker: 'def test_builtin_rule_line_ending_invariant',
    },
];
const codingQueueTestcases = [
    {
        testcaseName: 'sec-e2e-025-audit-integrity-self-healing-lockdown',
        entryPath: 'tests/integration/security/test_audit_foundation.py::test_audit_integrity_self_healing_lockdown',
        initialExecutionStatus: 'passed',
    },
    {
        testcaseName: 'sec-e2e-027-lease-expiry-active-defense',
        entryPath: 'tests/integration/security/test_audit_foundation.py::test_lease_expiry_blocks_untrusted_rejoin_until_gap_sync',
        initialExecutionStatus: 'passed',
    },
    {
        testcaseName: 'sec-e2e-028-normal-offline-reconnect-clear-state',
        entryPath: 'tests/integration/security/test_audit_foundation.py::test_normal_offline_reconnect_clears_without_gap_recovery',
        initialExecutionStatus: 'passed',
    },
    {
        testcaseName: 'sec-e2e-029-builtin-rule-line-ending-invariant',
        entryPath: 'extension/run-integrity-delivery-selftest.py',
        initialExecutionStatus: 'passed',
    },
];

function readJson(relativePath) {
    return JSON.parse(
        fs.readFileSync(path.join(repoRoot, ...relativePath.split('/')), 'utf8'),
    );
}

const graph = readJson('design/KG/SystemArchitecture.json');
const handoff = readJson('design/KG/ImplementationToCodingHandoff.json');
const failureRecords = readJson('design/KG/test-failure-records.json');
const explicitTestBody = fs.readFileSync(
    path.join(repoRoot, 'tests', 'integration', 'security', 'test_audit_foundation.py'),
    'utf8',
);
const harnessBody = fs.readFileSync(
    path.join(repoRoot, 'tests', 'integration', 'security', 'harness.py'),
    'utf8',
);
const integrationConftestBody = fs.readFileSync(
    path.join(repoRoot, 'tests', 'integration', 'conftest.py'),
    'utf8',
);

for (const explicitTestcase of frozenExplicitTestcases) {
    const graphTestcase = (graph.elements || [])
        .flatMap(element => element.testcases || [])
        .find(testcase => testcase.name === explicitTestcase.testcaseName);

    assert.ok(graphTestcase, `SystemArchitecture.json must include ${explicitTestcase.testcaseName}.`);
    assert.strictEqual(
        graphTestcase.acceptanceCriteria,
        explicitTestcase.entryPath,
        `${explicitTestcase.testcaseName} must stay mounted to the frozen explicit entrypoint.`,
    );

}

for (const explicitTestcase of codingQueueTestcases) {
    const handoffEntrypoint = (handoff.explicitEntrypoints || []).find(
        entry => entry.testcaseName === explicitTestcase.testcaseName,
    );
    assert.ok(handoffEntrypoint, `Implementation handoff must include ${explicitTestcase.testcaseName}.`);
    assert.strictEqual(
        handoffEntrypoint.entryPath,
        explicitTestcase.entryPath,
        'Implementation handoff must hand off the same explicit entrypoint path.',
    );
    assert.strictEqual(
        handoffEntrypoint.initialExecutionStatus,
        explicitTestcase.initialExecutionStatus,
        `The first ${explicitTestcase.testcaseName} execution status must match the recorded implementation handoff state.`,
    );

    const failureRecord = (failureRecords || []).find(
        record => record.testcasename === explicitTestcase.testcaseName,
    );
    if (explicitTestcase.initialExecutionStatus === 'failed') {
        assert.ok(
            failureRecord,
            `Failure records must preserve the first expected-failure signal for ${explicitTestcase.testcaseName}.`,
        );
        assert.strictEqual(
            failureRecord.resolvedScriptPath,
            explicitTestcase.entryPath,
            'Failure records must point back to the same explicit entrypoint path.',
        );
    } else {
        assert.ok(
            !failureRecord,
            `Failure records must not keep a stale failed entry for passing testcase ${explicitTestcase.testcaseName}.`,
        );
    }
}

assert.ok(
    !(handoff.codingTargets || []).some(
        target => target.testcaseName === 'sec-e2e-024-end-to-end-non-repudiation-evidence-chain',
    ),
    'Implementation handoff must not keep sec-e2e-024 in codingTargets after it has been implemented.',
);
assert.ok(
    !(handoff.codingTargets || []).some(
        target => target.testcaseName === 'sec-e2e-027-lease-expiry-active-defense'
        && String(target.failureSignal || '').startsWith('Lease_Expiry_Active_Defense_Gap'),
    ),
    'Implementation handoff must not keep a stale open sec-e2e-027 coding failure after the explicit gate is resolved.',
);
assert.ok(
    !(failureRecords || []).some(
        record => record.testcasename === 'sec-e2e-027-lease-expiry-active-defense',
    ),
    'Failure records must not keep a stale sec-e2e-027 failure after runArchitectureTests passes.',
);
const resolvedLeaseExpiryHandoff = (handoff.explicitEntrypoints || []).find(
    entry => entry.testcaseName === 'sec-e2e-027-lease-expiry-active-defense',
);
assert.ok(
    resolvedLeaseExpiryHandoff,
    'Implementation handoff must keep the sec-e2e-027 explicit entrypoint.',
);
assert.strictEqual(
    resolvedLeaseExpiryHandoff.initialExecutionStatus,
    'passed',
    'Resolved sec-e2e-027 handoff status must be passed after the full explicit gate is green.',
);
assert.ok(
    !(handoff.codingTargets || []).some(
        target => target.testcaseName === 'sec-e2e-028-normal-offline-reconnect-clear-state'
        && String(target.failureSignal || '').startsWith('Normal_Offline_Reconnect_Clear_State_Gap'),
    ),
    'Implementation handoff must not keep a stale open sec-e2e-028 coding failure after the explicit gate is resolved.',
);
assert.ok(
    !(failureRecords || []).some(
        record => record.testcasename === 'sec-e2e-028-normal-offline-reconnect-clear-state',
    ),
    'Failure records must not keep a stale sec-e2e-028 failure after runArchitectureTests passes.',
);
const resolvedNormalReconnectHandoff = (handoff.explicitEntrypoints || []).find(
    entry => entry.testcaseName === 'sec-e2e-028-normal-offline-reconnect-clear-state',
);
assert.ok(
    resolvedNormalReconnectHandoff,
    'Implementation handoff must keep the resolved sec-e2e-028 explicit entrypoint.',
);
assert.strictEqual(
    resolvedNormalReconnectHandoff.initialExecutionStatus,
    'passed',
    'Resolved sec-e2e-028 handoff status must be passed after the full explicit gate is green.',
);
assert.ok(
    !(handoff.codingTargets || []).some(
        target => target.testcaseName === 'sec-e2e-029-builtin-rule-line-ending-invariant',
    ),
    'Implementation handoff must not keep sec-e2e-029 in codingTargets after the explicit gate is resolved.',
);
assert.ok(
    !(failureRecords || []).some(
        record => record.testcasename === 'sec-e2e-029-builtin-rule-line-ending-invariant',
    ),
    'Failure records must not keep a stale sec-e2e-029 failure after runArchitectureTests passes.',
);
const resolvedLineEndingHandoff = (handoff.explicitEntrypoints || []).find(
    entry => entry.testcaseName === 'sec-e2e-029-builtin-rule-line-ending-invariant',
);
assert.ok(
    resolvedLineEndingHandoff,
    'Implementation handoff must keep the resolved sec-e2e-029 explicit entrypoint.',
);
assert.strictEqual(
    resolvedLineEndingHandoff.initialExecutionStatus,
    'passed',
    'Resolved sec-e2e-029 handoff status must be passed after the full explicit gate is green.',
);

const toolGuardRulesIntegrityTestBody = fs.readFileSync(
    path.join(repoRoot, 'tests', 'unit', 'security', 'tool_guard', 'test_rules_integrity.py'),
    'utf8',
);
const toolGuardRulesIntegrityHarnessBody = fs.readFileSync(
    path.join(repoRoot, 'tests', 'unit', 'security', 'tool_guard', 'harness.py'),
    'utf8',
);

for (const marker of [
    '# GIVEN',
    '# WHEN',
    '# THEN',
    'def test_builtin_rule_line_ending_invariant',
    'def test_sha256_normalized_content_shared_helper_contract',
    'Line_Ending_Invariant_Gap',
    'Rules_Integrity_Status_Projection_Gap',
    'Semantic_Tamper_Detection_Gap',
    'Normalized_Content_Hash_Drift',
    'Manifest_Baseline_Digest_Mismatch',
    'Manifest_Runtime_Hash_Drift',
]) {
    assert.ok(
        toolGuardRulesIntegrityTestBody.includes(marker) || toolGuardRulesIntegrityHarnessBody.includes(marker),
        `The frozen sec-e2e-029 entrypoint must keep the marker: ${marker}`,
    );
}

for (const marker of [
    '# // GIVEN',
    '# // WHEN',
    '# // THEN',
    'app_server',
    'def test_end_to_end_non_repudiation_evidence_chain',
    'def test_audit_integrity_self_healing_lockdown',
    'def test_lease_expiry_blocks_untrusted_rejoin_until_gap_sync',
    'def test_normal_offline_reconnect_clears_without_gap_recovery',
    'def test_prompt_injection_cannot_bypass_high_risk_tool_guard',
    'for_app_server',
    'expect_context_propagation',
    'get_last_audit_record_from_disk',
    'verify_local_hash_chain_integrity',
    'verify_confirmation_precedes_high_risk_tool_effect',
    'verify_tamper_evidence_forces_lockdown',
    'baseline_high_risk_action_labels',
    'tampered_record_position_from_start',
    'second_committed_audit_record_history_edit',
    'verify_lease_expiry_blocks_untrusted_rejoin_until_gap_sync',
    'verify_normal_offline_reconnect_clears_without_gap_recovery',
    'recovery_control_point_ready',
    'runtime_restarted_before_lease_expiry',
    'backend_clear_projection_ready',
    'no_gap_validation_required',
    'pre_recovery_lease_monitor_projection_ready',
    'post_recovery_backend_api_projection_ready',
    'post_recovery_operator_web_projection_ready',
    'verify_prompt_injection_guard_enforced',
    'render_non_repudiation_failure_report',
    'render_audit_integrity_lockdown_failure_report',
    'render_lease_expiry_failure_report',
    'render_normal_offline_reconnect_failure_report',
    'render_prompt_injection_guard_failure_report',
    'security_center_backend_api_name',
    'security_center_operator_web_name',
    'lease_monitor_name',
    'missing_gap_verification_label',
    'backend_api_projection_ready',
    'operator_web_projection_ready',
    'backend_api_rejection_ready',
    'operator_web_rejection_ready',
]) {
    assert.ok(
        explicitTestBody.includes(marker),
        `The explicit sec-e2e-024 entrypoint must keep the frozen runtime-inspection marker: ${marker}`,
    );
}

for (const categoryMarker of [
    'category="Non_Repudiation_Gap"',
    'category="Audit_Integrity_Lockdown_Gap"',
    'category="Lease_Expiry_Active_Defense_Gap"',
    'category="Normal_Offline_Reconnect_Clear_State_Gap"',
    'category="Prompt_Injection_Guard_Gap"',
    'pre_recovery_console_status',
    'post_recovery_console_status',
    'Recovery_Control_Point_Missing',
    'Security_Rejection_Nonce',
    'Security_Center_Backend_Api_Missing',
    'Security_Center_Operator_Web_Missing',
    'Historical_Multi_Record_Baseline_Missing',
    'Second_Historical_Record_Tamper_Missing',
    'Historical_Record_Tamper_Not_Detected',
    'Security_Center_Clear_State_Not_Blocked',
    'Lease_Heartbeat_Projection_Missing',
    'Normal_Reconnect_Backend_Clear_State_Missing',
    'Normal_Reconnect_Gap_Validation_False_Positive',
    'Normal_Reconnect_Model_Access_200_Missing',
]) {
    assert.ok(
        harnessBody.includes(categoryMarker),
        `The protected harness must keep the business failure marker: ${categoryMarker}`,
    );
}

for (const harnessMethod of [
    'for_app_server',
    'expect_context_propagation',
    'get_last_audit_record_from_disk',
    'verify_local_hash_chain_integrity',
    'verify_confirmation_precedes_high_risk_tool_effect',
    'verify_tamper_evidence_forces_lockdown',
    '_tamper_committed_historical_audit_record',
    'verify_lease_expiry_blocks_untrusted_rejoin_until_gap_sync',
    '_attempt_missing_gap_verification',
    'verify_normal_offline_reconnect_clears_without_gap_recovery',
    '_restart_runtime_normally_before_lease_expiry',
    'verify_prompt_injection_guard_enforced',
    'render_non_repudiation_failure_report',
    'render_audit_integrity_lockdown_failure_report',
    'render_lease_expiry_failure_report',
    'render_normal_offline_reconnect_failure_report',
    'render_prompt_injection_guard_failure_report',
]) {
    assert.ok(
        harnessBody.includes(`def ${harnessMethod}`),
        `The protected harness must keep the method ${harnessMethod}.`,
    );
}

for (const marker of [
    'startup_error',
    'raise AssertionError(self.startup_error)',
]) {
    assert.ok(
        integrationConftestBody.includes(marker),
        `The shared real-environment bootstrap must keep the readable startup marker: ${marker}`,
    );
}

console.log('security explicit entrypoint traceability ok');
