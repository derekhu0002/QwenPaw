const assert = require('assert');
const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..', '..');

function read(relativePath) {
    return fs.readFileSync(path.join(repoRoot, ...relativePath.split('/')), 'utf8');
}

const securityCenterApi = read('deploy/api/app.py');
const securityCenterStore = read('deploy/api/store.py');

assert.ok(
    securityCenterApi.includes('lease_ttl_seconds'),
    'Security Center API request contract must keep lease_ttl_seconds on RecoveryHandshakeRequest so runtime heartbeat TTL reaches the durable store.',
);

assert.ok(
    securityCenterStore.includes('if "lease_ttl_seconds" in payload:'),
    'Security Center store must keep an explicit branch that persists runtime heartbeat lease timing when the API request carries lease_ttl_seconds.',
);

assert.ok(
    securityCenterStore.includes('"last_heartbeat_at": requested_at_ns')
        && securityCenterStore.includes('"lease_ttl_seconds": lease_ttl_seconds')
        && securityCenterStore.includes('"lease_expires_at": requested_at_ns + (lease_ttl_seconds * 1_000_000_000)'),
    'Security Center store must durably write last_heartbeat_at, lease_ttl_seconds, and lease_expires_at for the canonical runtime client instead of leaving those lease fields implicit.',
);

assert.ok(
    !securityCenterStore.includes('if last_heartbeat_at <= 0 and str(projected.get("last_handshake_trace_id") or "").startswith("runtime-heartbeat::")'),
    'Security Center overview and timeline must not synthesize runtime heartbeat lease timing from updated_at_ns when the durable store lacks heartbeat timestamps; implementation must persist lease timing instead of hiding the gap in read models.',
);

console.log('security runtime lease persistence boundary ok');