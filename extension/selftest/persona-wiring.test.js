/**
 * Extension wiring check for the Persona Protection self-test net.
 * Ensures manifest targets, host bridges, and scenario markers stay aligned.
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..', '..');

function read(relativePath) {
    return fs.readFileSync(path.join(repoRoot, ...relativePath.split('/')), 'utf8');
}

function readJson(relativePath) {
    return JSON.parse(read(relativePath));
}

function exists(relativePath) {
    return fs.existsSync(path.join(repoRoot, ...relativePath.split('/')));
}

const manifest = readJson('scripts/persona-protection-selftest.manifest.json');
const integrityTestBody = read('tests/integration/security/test_integrity_protection.py');

assert.strictEqual(manifest.name, 'persona-protection-selftest');

for (const layerName of ['wiring', 'backend', 'frontend']) {
    const layer = manifest.layers[layerName];
    assert.ok(Array.isArray(layer.targets) && layer.targets.length > 0, `${layerName} targets missing`);
    if (layerName === 'backend') {
        assert.ok(exists(layer.module), `missing backend module: ${layer.module}`);
        continue;
    }
    for (const target of layer.targets) {
        const relative = layerName === 'frontend' ? path.join('console', target) : target;
        assert.ok(exists(relative), `missing ${layerName} target: ${relative}`);
    }
}

for (const testName of manifest.layers.backend.targets) {
    const marker = `def ${testName}`;
    assert.ok(
        integrityTestBody.includes(marker),
        `backend manifest target not found in test module: ${marker}`,
    );
}

const requiredWiring = [
    'extension/persona_baseline/emitter.py',
    'extension/persona_baseline/service.py',
    'extension/persona_baseline/host_bridge.py',
    'src/qwenpaw/security/extension_host.py',
    'src/qwenpaw/security/persona_baseline_bridge.py',
    'src/qwenpaw/app/routers/persona_protection_routes.py',
    'console/src/extension/persona_baseline/components/PersonaDriftAlertNotifier/index.tsx',
    'console/src/extension/persona_baseline/lib/alertActions.ts',
    'console/src/pages/Settings/Security/components/IntegrityCheckSection.tsx',
];

for (const filePath of requiredWiring) {
    assert.ok(exists(filePath), `persona wiring file missing: ${filePath}`);
}

const bridgeBody = read('src/qwenpaw/security/persona_baseline_bridge.py');
const hostBridgeBody = read('extension/persona_baseline/host_bridge.py');
assert.ok(
    hostBridgeBody.includes('push_append'),
    'persona host bridge must wire inbox/push emitters',
);
assert.ok(
    bridgeBody.includes('get_persona_service'),
    'persona bridge must re-export service accessor',
);

const notifierBody = read('console/src/extension/persona_baseline/components/PersonaDriftAlertNotifier/index.tsx');
assert.ok(notifierBody.includes('restorePersonaAlert'), 'notifier must call restorePersonaAlert');
assert.ok(notifierBody.includes('acceptPersonaAlert'), 'notifier must call acceptPersonaAlert');
assert.ok(
    notifierBody.includes('alertActions'),
    'notifier must use shared persona actions',
);

const scenarioIds = new Set(manifest.scenarios.map((item) => item.id));
const expectedScenarioIds = [
    'PB-S02',
    'PB-S10',
    'PB-S30',
    'PB-S40',
    'PB-S42',
    'PB-S50',
    'PB-SUI-NOTIFIER',
];
for (const scenarioId of expectedScenarioIds) {
    assert.ok(scenarioIds.has(scenarioId), `manifest scenario missing: ${scenarioId}`);
}

console.log(
    `persona-wiring: manifest v${manifest.version} ok ` +
        `(${manifest.layers.backend.targets.length} backend, ` +
        `${manifest.layers.frontend.targets.length} frontend targets)`,
);
