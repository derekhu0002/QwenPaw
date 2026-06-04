const assert = require('assert');
const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..', '..');

function read(relativePath) {
    return fs.readFileSync(path.join(repoRoot, ...relativePath.split('/')), 'utf8');
}

for (const relativePath of [
    'src/qwenpaw/security/ARCHITECTURE.md',
    'deploy/ARCHITECTURE.md',
    'deploy/api/ARCHITECTURE.md',
    'deploy/web/ARCHITECTURE.md',
    'tests/integration/security/ARCHITECTURE.md',
    'tests/integration/security/harness.py',
    'tests/integration/security/test_audit_foundation.py',
    'design/KG/ImplementationToCodingHandoff.json',
]) {
    assert.ok(
        fs.existsSync(path.join(repoRoot, ...relativePath.split('/'))),
        `Missing frozen security boundary artifact: ${relativePath}`,
    );
}

const overallArchitecture = read('OVERALL_ARCHITECTURE.md');
const runtimeArchitecture = read('src/qwenpaw/ARCHITECTURE.md');
const securityArchitecture = read('src/qwenpaw/security/ARCHITECTURE.md');
const deployArchitecture = read('deploy/ARCHITECTURE.md');
const deployApiArchitecture = read('deploy/api/ARCHITECTURE.md');
const deployWebArchitecture = read('deploy/web/ARCHITECTURE.md');
const testsArchitecture = read('tests/ARCHITECTURE.md');
const securityTestsArchitecture = read('tests/integration/security/ARCHITECTURE.md');

for (const contractPath of [
    'src/qwenpaw/security/ARCHITECTURE.md',
    'tests/integration/security/ARCHITECTURE.md',
    'deploy/ARCHITECTURE.md',
    'deploy/api/ARCHITECTURE.md',
    'deploy/web/ARCHITECTURE.md'
]) {
    assert.ok(
        overallArchitecture.includes(contractPath),
        `OVERALL_ARCHITECTURE.md must reference ${contractPath}`,
    );
}

assert.ok(
    runtimeArchitecture.includes('path: security'),
    'src/qwenpaw/ARCHITECTURE.md must keep security as a stable child boundary.',
);
assert.ok(
    securityArchitecture.includes(
        'tests/integration/security/test_audit_foundation.py::test_end_to_end_non_repudiation_evidence_chain',
    ),
    'Security contract must name the sec-e2e-024 explicit entrypoint.',
);
assert.ok(
    securityArchitecture.includes(
        'tests/integration/security/test_audit_foundation.py::test_audit_integrity_self_healing_lockdown',
    ),
    'Security contract must name the sec-e2e-025 explicit entrypoint.',
);
assert.ok(
    securityArchitecture.includes(
        'tests/integration/security/test_audit_foundation.py::test_prompt_injection_cannot_bypass_high_risk_tool_guard',
    ),
    'Security contract must name the sec-e2e-021 explicit entrypoint.',
);
assert.ok(
    testsArchitecture.includes(
        'integration/security/test_audit_foundation.py::test_end_to_end_non_repudiation_evidence_chain',
    ),
    'tests/ARCHITECTURE.md must list the sec-e2e-024 explicit entrypoint.',
);
assert.ok(
    testsArchitecture.includes(
        'integration/security/test_audit_foundation.py::test_audit_integrity_self_healing_lockdown',
    ),
    'tests/ARCHITECTURE.md must list the sec-e2e-025 explicit entrypoint.',
);
assert.ok(
    testsArchitecture.includes(
        'integration/security/test_audit_foundation.py::test_prompt_injection_cannot_bypass_high_risk_tool_guard',
    ),
    'tests/ARCHITECTURE.md must list the sec-e2e-021 explicit entrypoint.',
);
assert.ok(
    securityTestsArchitecture.includes('harness.py'),
    'The explicit security entrypoint zone must protect the local harness fixture.',
);
assert.ok(
    deployArchitecture.includes('Security Center'),
    'deploy/ARCHITECTURE.md must keep Security Center as a separate stable deployment boundary.',
);
assert.ok(
    deployArchitecture.includes('HTTP only'),
    'deploy/ARCHITECTURE.md must freeze edge-to-cloud access to HTTP only.',
);
assert.ok(
    deployApiArchitecture.includes('backend HTTP API service'),
    'deploy/api/ARCHITECTURE.md must freeze the backend HTTP API role.',
);
assert.ok(
    deployApiArchitecture.includes('Server-Sent Events (SSE) or WebSocket'),
    'deploy/api/ARCHITECTURE.md must freeze an SSE or WebSocket operator alert stream.',
);
assert.ok(
    deployApiArchitecture.includes('under 500ms'),
    'deploy/api/ARCHITECTURE.md must freeze sub-500ms operator alert delivery.',
);
assert.ok(
    deployWebArchitecture.includes('operator-facing web frontend'),
    'deploy/web/ARCHITECTURE.md must freeze the operator web role.',
);
assert.ok(
    deployWebArchitecture.includes('hash-break curve chart'),
    'deploy/web/ARCHITECTURE.md must freeze the hash-break curve chart requirement.',
);
assert.ok(
    deployWebArchitecture.includes('Voucher'),
    'deploy/web/ARCHITECTURE.md must freeze nonce voucher visibility.',
);
assert.ok(
    deployWebArchitecture.includes('manual refresh'),
    'deploy/web/ARCHITECTURE.md must forbid manual-refresh-only alerting.',
);

console.log('security audit contract boundaries ok');
