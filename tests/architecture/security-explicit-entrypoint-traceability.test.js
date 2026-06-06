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
];
const codingQueueTestcases = [
    {
        testcaseName: 'sec-e2e-027-lease-expiry-active-defense',
        entryPath: 'tests/integration/security/test_audit_foundation.py::test_lease_expiry_blocks_untrusted_rejoin_until_gap_sync',
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
    !(handoff.explicitEntrypoints || []).some(
        entry => entry.testcaseName === 'sec-e2e-024-end-to-end-non-repudiation-evidence-chain',
    ),
    'Implementation handoff must not keep sec-e2e-024 in the coding queue after it has been implemented.',
);

for (const marker of [
    '# // GIVEN',
    '# // WHEN',
    '# // THEN',
    'app_server',
    'def test_end_to_end_non_repudiation_evidence_chain',
    'def test_audit_integrity_self_healing_lockdown',
    'def test_lease_expiry_blocks_untrusted_rejoin_until_gap_sync',
    'def test_prompt_injection_cannot_bypass_high_risk_tool_guard',
    'for_app_server',
    'expect_context_propagation',
    'get_last_audit_record_from_disk',
    'verify_local_hash_chain_integrity',
    'verify_confirmation_precedes_high_risk_tool_effect',
    'verify_tamper_evidence_forces_lockdown',
    'verify_lease_expiry_blocks_untrusted_rejoin_until_gap_sync',
    'recovery_control_point_ready',
    'pre_recovery_lease_monitor_projection_ready',
    'post_recovery_backend_api_projection_ready',
    'post_recovery_operator_web_projection_ready',
    'verify_prompt_injection_guard_enforced',
    'render_non_repudiation_failure_report',
    'render_audit_integrity_lockdown_failure_report',
    'render_lease_expiry_failure_report',
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
    'category="Prompt_Injection_Guard_Gap"',
    'pre_recovery_console_status',
    'post_recovery_console_status',
    'Recovery_Control_Point_Missing',
    'Security_Rejection_Nonce',
    'Security_Center_Backend_Api_Missing',
    'Security_Center_Operator_Web_Missing',
    'Lease_Heartbeat_Projection_Missing',
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
    'verify_lease_expiry_blocks_untrusted_rejoin_until_gap_sync',
    '_attempt_missing_gap_verification',
    'verify_prompt_injection_guard_enforced',
    'render_non_repudiation_failure_report',
    'render_audit_integrity_lockdown_failure_report',
    'render_lease_expiry_failure_report',
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
