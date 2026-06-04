---
contract_type: implementation-architecture-element
contract_version: 1
scope: stable-element
element_name: security-center-deployment-boundary
element_kind: SecurityCenterDeploymentBoundary
element_path: deploy
---

## Implementation Architecture Contract

### Responsibility
- Own the stable repository deployment boundary for the physically separate Security Center process.
- Preserve the cloud-side integrity mirror, rejected-event projection, and recovery-handshake bootstrap as an independent fact source reached only through audit uplink.
- Freeze the deploy-owned decomposition into a backend HTTP API service plus an operator-facing web frontend.
- Freeze the real-time operator alert path: deploy/api must publish Security_Rejection_Nonce and hash-divergence updates to deploy/web through Server-Sent Events (SSE) or WebSocket rather than operator polling.
- Freeze the boundary where container bootstrap assets, runtime configuration, cloud-side durable storage, HTTP ingress, and operator web delivery will be materialized during Coding/Repair.

### Out Of Scope
- Owning edge runtime behavior under src/qwenpaw/.
- Reading or sharing the edge node's local working directory directly.
- Rehosting Security Center logic inside the edge process or explicit testcase bodies.

### Children
- path: api
  kind: security-center-backend-api
  role: stable backend service boundary that receives edge HTTP uplinks, exposes operator-facing query APIs and push streams, and owns cloud-side shadow-state comparison
- path: web
  kind: security-center-operator-web
  role: stable frontend boundary that renders anomaly, rejection, recovery state, hash-break curve charts, nonce vouchers, and real-time red alerts for human operators by consuming the backend API
- path: Dockerfile
  kind: deployment-bootstrap
  role: container build contract for the separate Security Center process
- path: entrypoint.sh
  kind: runtime-bootstrap
  role: process startup contract for the separate Security Center boundary
- path: config
  kind: deployment-config
  role: stable configuration zone for the Security Center deployment environment

### Dependency Direction
- deploy/ may consume uplink summaries from the edge runtime, but it must not read local edge files or share the edge durable store.
- Edge runtime access to Security Center is frozen to HTTP only. The edge must not import deploy code as a library, mount deploy storage, or bypass the backend API through direct database or file access.
- deploy/web depends on deploy/api for operator-visible state and push delivery, must not be used as a backchannel from the edge runtime, and must not rely on manual refresh for Security_Rejection_Nonce alerting.
- tests/integration/security may observe cloud-visible results only through the stable projection seam owned by this boundary.
- src/qwenpaw/security owns edge-side evidence production and uplink initiation; deploy/api owns cloud-side HTTP reception, shadow-state comparison, SSE or WebSocket alert publication, and operator query APIs; deploy/web owns operator-facing anomaly projection, hash-break visualization, nonce voucher display, and sub-500ms red-alert rendering.

### Notes
- Current repository evidence only confirms deployment bootstrap assets, not a realized cloud-side intake, HTTP API service, operator web, or shadow-hash service.
- Coding/Repair must materialize a separate process and durable store behind this contract rather than collapsing Security Center into src/qwenpaw/security or into the test harness.
