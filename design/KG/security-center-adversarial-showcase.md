# Security Center Adversarial Showcase

This showcase closes coding-task-006 by giving operators a repeatable script that demonstrates physical tamper detection, fork-point tracing, and blind prompt-injection rejection against the materialized deploy/api and deploy/web boundaries.

## Physical Tamper Showcase

Control point: Use a Hex Editor to alter bytes in the local durable audit store after one approved high-risk action, remove or invalidate the checkpoint anchor, restart the edge runtime, and attempt another sensitive action.

Observation point: The edge runtime enters `UNTRUSTED`, `deploy/api` exposes a recovery-required handshake status plus a divergence timeline, and `deploy/web` renders the hash-break curve chart with the first divergent Event ID as the fork point.

## Fork Tracing Showcase

Control point: Query `GET /security-center/v1/operator/timelines/{client_id}` after the lockdown uplink and load the same client in `deploy/web`.

Observation point: The timeline response and the rendered chart both show separate local-hash and cloud-shadow-hash lines with one explicit fork marker, and the operator can name the first divergent Event ID without opening the edge node's local files from the cloud side.

## Blind Prompt Injection Showcase

Control point: Let an evaluator provide an unpublished prompt, then post the resulting rejection through `python -m deploy.api.showcase seed-rejection --prompt "<blind prompt>"` or through the edge runtime when `QWENPAW_SECURITY_CENTER_API_URL` is configured.

Observation point: `deploy/api` persists a non-static `Security_Rejection_Nonce`, exposes it as a Voucher lookup result, and `deploy/web` auto-pops a red alert with perceived latency derived from `edge_timestamp_ns` instead of a polling loop.
