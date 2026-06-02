const assert = require('assert');
const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..', '..');
const packageJson = JSON.parse(
    fs.readFileSync(path.join(repoRoot, 'package.json'), 'utf8'),
);
const validatorContract = fs.readFileSync(
    path.join(repoRoot, '.github', 'validator', 'ARCHITECTURE.md'),
    'utf8',
);

const expectedScripts = {
    'validate:system-architecture': 'node .github/validator/script/validateSystemArchitecture.js',
    'validate:handoff:intent': 'node .github/validator/script/validateStageHandoff.js intent-to-implementation',
    'validate:handoff:implementation': 'node .github/validator/script/validateStageHandoff.js implementation-to-coding',
    'test:argo': 'node .github/validator/script/runArchitectureTests.js'
};

for (const [scriptName, expectedCommand] of Object.entries(expectedScripts)) {
    assert.strictEqual(
        packageJson.scripts[scriptName],
        expectedCommand,
        `package.json script ${scriptName} must stay aligned with bundled validator assets`,
    );
}

for (const relativePath of [
    '.github/validator/script/validateSystemArchitecture.js',
    '.github/validator/script/validateStageHandoff.js',
    '.github/validator/script/runArchitectureTests.js'
]) {
    assert.ok(
        fs.existsSync(path.join(repoRoot, ...relativePath.split('/'))),
        `Missing bundled validator asset: ${relativePath}`,
    );
    assert.ok(
        validatorContract.includes(relativePath.replace('.github/validator/', '')) || validatorContract.includes(relativePath),
        `Validator contract must mention ${relativePath}`,
    );
}

assert.ok(
    validatorContract.includes('package.json'),
    'Validator contract must describe the package.json wiring it protects.',
);

console.log('validator bootstrap traceability ok');