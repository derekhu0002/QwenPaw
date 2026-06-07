const assert = require('assert');
const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..', '..');

function read(relativePath) {
    return fs.readFileSync(path.join(repoRoot, ...relativePath.split('/')), 'utf8');
}

const auditFoundation = read('src/qwenpaw/security/audit_foundation.py');
const securityCenterStore = read('deploy/api/store.py');

assert.ok(
    auditFoundation.includes('def emit_runtime_lease_heartbeat'),
    'Runtime security boundary must keep an explicit runtime heartbeat emitter seam.',
);
assert.ok(
    auditFoundation.includes('def preflight_sensitive_action_recovery'),
    'Runtime security boundary must keep a recovery preflight seam.',
);

assert.ok(
    !(
        auditFoundation.includes('resolved_session_id = session_id or runtime_lease_client_id(base_dir)')
        && auditFoundation.includes('"client_id": resolved_session_id')
        && auditFoundation.includes('"client_id": session_id')
    ),
    'Heartbeat registration, recovery preflight, lockdown, and restored-access projection must share one canonical Security Center client id; current code still splits startup heartbeat to runtime-heartbeat::<fingerprint> while later security flows continue to use raw session_id.',
);

assert.ok(
    !securityCenterStore.includes('client_id.startswith("runtime-heartbeat::")'),
    'Security Center must not special-case runtime-heartbeat::<fingerprint> as a separate bootstrap-only terminal identity; heartbeat and later audit-chain continuity must converge on one canonical runtime client id.',
);

console.log('security runtime client identity boundary ok');