const assert = require('assert');
const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..', '..');

function read(relativePath) {
    return fs.readFileSync(path.join(repoRoot, ...relativePath.split('/')), 'utf8');
}

for (const relativePath of [
    'src/qwenpaw/security/ARCHITECTURE.md',
    'tests/integration/security/ARCHITECTURE.md',
    'tests/integration/security/harness.py',
    'tests/integration/security/test_audit_foundation.py'
]) {
    assert.ok(
        fs.existsSync(path.join(repoRoot, ...relativePath.split('/'))),
        `Missing frozen security boundary artifact: ${relativePath}`,
    );
}

const overallArchitecture = read('OVERALL_ARCHITECTURE.md');
const runtimeArchitecture = read('src/qwenpaw/ARCHITECTURE.md');
const securityArchitecture = read('src/qwenpaw/security/ARCHITECTURE.md');
const testsArchitecture = read('tests/ARCHITECTURE.md');
const securityTestsArchitecture = read('tests/integration/security/ARCHITECTURE.md');

for (const contractPath of [
    'src/qwenpaw/security/ARCHITECTURE.md',
    'tests/integration/security/ARCHITECTURE.md'
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
    testsArchitecture.includes(
        'integration/security/test_audit_foundation.py::test_end_to_end_non_repudiation_evidence_chain',
    ),
    'tests/ARCHITECTURE.md must list the sec-e2e-024 explicit entrypoint.',
);
assert.ok(
    securityTestsArchitecture.includes('harness.py'),
    'The explicit security entrypoint zone must protect the local harness fixture.',
);

console.log('security audit contract boundaries ok');
