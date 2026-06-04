const assert = require('assert');
const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..', '..');

const requiredFiles = [
    'design/KG/SystemArchitecture.json',
    'design/KG/IntentToImplementationHandoff.json',
    'design/KG/ImplementationToCodingHandoff.json',
    'design/KG/test-failure-records.json',
    'OVERALL_ARCHITECTURE.md',
    'src/qwenpaw/ARCHITECTURE.md',
    'src/qwenpaw/security/ARCHITECTURE.md',
    'src/qwenpaw/cli/ARCHITECTURE.md',
    'console/ARCHITECTURE.md',
    'website/ARCHITECTURE.md',
    'deploy/ARCHITECTURE.md',
    'deploy/api/ARCHITECTURE.md',
    'deploy/web/ARCHITECTURE.md',
    'tests/ARCHITECTURE.md',
    'tests/integration/security/ARCHITECTURE.md',
    'tests/integration/security/test_audit_foundation.py',
    '.github/validator/ARCHITECTURE.md'
];

for (const relativePath of requiredFiles) {
    const absolutePath = path.join(repoRoot, ...relativePath.split('/'));
    assert.ok(fs.existsSync(absolutePath), `Missing required architecture file: ${relativePath}`);
}

const overallArchitecture = fs.readFileSync(
    path.join(repoRoot, 'OVERALL_ARCHITECTURE.md'),
    'utf8',
);

for (const contractPath of [
    'src/qwenpaw/ARCHITECTURE.md',
    'src/qwenpaw/security/ARCHITECTURE.md',
    'src/qwenpaw/cli/ARCHITECTURE.md',
    'console/ARCHITECTURE.md',
    'website/ARCHITECTURE.md',
    'deploy/ARCHITECTURE.md',
    'deploy/api/ARCHITECTURE.md',
    'deploy/web/ARCHITECTURE.md',
    'tests/ARCHITECTURE.md',
    'tests/integration/security/ARCHITECTURE.md',
    '.github/validator/ARCHITECTURE.md'
]) {
    assert.ok(
        overallArchitecture.includes(contractPath),
        `OVERALL_ARCHITECTURE.md must reference ${contractPath}`,
    );
}

const graph = JSON.parse(
    fs.readFileSync(path.join(repoRoot, 'design', 'KG', 'SystemArchitecture.json'), 'utf8'),
);

assert.ok(Array.isArray(graph.elements) && graph.elements.length >= 5, 'System architecture graph must include stable current-state elements.');
assert.ok(Array.isArray(graph.views) && graph.views.length >= 1, 'System architecture graph must include at least one view.');
