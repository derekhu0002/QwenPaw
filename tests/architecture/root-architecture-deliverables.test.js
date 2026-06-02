const assert = require('assert');
const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..', '..');

const REQUIRED_PATHS = [
    'OVERALL_ARCHITECTURE.md',
    'src/qwenpaw/ARCHITECTURE.md',
    'console/ARCHITECTURE.md',
    'website/ARCHITECTURE.md',
    'tests/ARCHITECTURE.md',
    'tests/architecture/ARCHITECTURE.md',
    'design/KG/SystemArchitecture.json',
    'design/KG/IntentToImplementationHandoff.json',
    'design/KG/ImplementationToCodingHandoff.json',
];

function main() {
    for (const relativePath of REQUIRED_PATHS) {
        const absolutePath = path.join(repoRoot, relativePath);
        assert.ok(fs.existsSync(absolutePath), `Missing architecture deliverable: ${relativePath}`);
    }
    console.log('root architecture deliverables present');
}

main();