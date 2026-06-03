const assert = require('assert');
const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..', '..');
const explicitEntrypoint = 'tests/integration/security/test_audit_foundation.py::test_end_to_end_non_repudiation_evidence_chain';
const testcaseName = 'sec-e2e-024-end-to-end-non-repudiation-evidence-chain';

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

const graphTestcase = (graph.elements || [])
    .flatMap(element => element.testcases || [])
    .find(testcase => testcase.name === testcaseName);

assert.ok(graphTestcase, `SystemArchitecture.json must include ${testcaseName}.`);
assert.strictEqual(
    graphTestcase.acceptanceCriteria,
    explicitEntrypoint,
    `${testcaseName} must stay mounted to the frozen explicit entrypoint.`,
);

const handoffEntrypoint = (handoff.explicitEntrypoints || []).find(
    entry => entry.testcaseName === testcaseName,
);
assert.ok(handoffEntrypoint, `Implementation handoff must include ${testcaseName}.`);
assert.strictEqual(
    handoffEntrypoint.entryPath,
    explicitEntrypoint,
    'Implementation handoff must hand off the same explicit entrypoint path.',
);
assert.strictEqual(
    handoffEntrypoint.initialExecutionStatus,
    'failed',
    'The first sec-e2e-024 execution should currently fail until Coding/Repair realizes the audit foundation.',
);

const failureRecord = (failureRecords || []).find(
    record => record.testcasename === testcaseName,
);
assert.ok(
    failureRecord,
    'Failure records must preserve the first expected-failure signal for sec-e2e-024.',
);
assert.strictEqual(
    failureRecord.resolvedScriptPath,
    explicitEntrypoint,
    'Failure records must point back to the same explicit entrypoint path.',
);

for (const marker of [
    '# // GIVEN',
    '# // WHEN',
    '# // THEN',
    'expect_context_propagation',
    'get_last_audit_record_from_disk',
    'verify_local_hash_chain_integrity',
    'verify_confirmation_precedes_high_risk_tool_effect',
    'render_non_repudiation_failure_report',
]) {
    assert.ok(
        explicitTestBody.includes(marker),
        `The explicit sec-e2e-024 entrypoint must keep the frozen runtime-inspection marker: ${marker}`,
    );
}

for (const harnessMethod of [
    'expect_context_propagation',
    'get_last_audit_record_from_disk',
    'verify_local_hash_chain_integrity',
    'verify_confirmation_precedes_high_risk_tool_effect',
    'render_non_repudiation_failure_report',
]) {
    assert.ok(
        harnessBody.includes(`def ${harnessMethod}`),
        `The protected harness must keep the method ${harnessMethod}.`,
    );
}

console.log('security explicit entrypoint traceability ok');
