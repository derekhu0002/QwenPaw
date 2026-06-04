const assert = require('assert');
const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..', '..');

const REQUIRED_PATHS = [
    'OVERALL_ARCHITECTURE.md',
    'src/qwenpaw/ARCHITECTURE.md',
    'src/qwenpaw/security/ARCHITECTURE.md',
    'console/ARCHITECTURE.md',
    'website/ARCHITECTURE.md',
    'deploy/ARCHITECTURE.md',
    'deploy/api/ARCHITECTURE.md',
    'deploy/web/ARCHITECTURE.md',
    'tests/ARCHITECTURE.md',
    'tests/architecture/ARCHITECTURE.md',
    'tests/integration/security/ARCHITECTURE.md',
    'tests/integration/security/test_audit_foundation.py',
    'tests/integration/security/harness.py',
    'design/KG/SystemArchitecture.json',
    'design/KG/IntentToImplementationHandoff.json',
    'design/KG/ImplementationToCodingHandoff.json',
    'design/KG/test-failure-records.json',
];

function main() {
    for (const relativePath of REQUIRED_PATHS) {
        const absolutePath = path.join(repoRoot, relativePath);
        assert.ok(fs.existsSync(absolutePath), `Missing architecture deliverable: ${relativePath}`);
    }
    console.log('root architecture deliverables present');
}

main();
