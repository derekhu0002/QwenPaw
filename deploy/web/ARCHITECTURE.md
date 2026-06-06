---
contract_type: implementation-architecture-element
contract_version: 1
scope: stable-element
element_name: security-center-operator-web
element_kind: SecurityCenterOperatorWeb
element_path: deploy/web
---

## Implementation Architecture Contract

### Responsibility
- Own the operator-facing web frontend for Security Center.
- Present anomaly, rejected-event, trust-state, and recovery-progress views to human operators.
- Present anomaly, lease-expiry `UNTRUSTED` state, rejected-event, trust-state, and recovery-progress views to human operators.
- Present a hash-break curve chart that shows the local hash and cloud shadow hash as separate lines and visually marks the fork point when divergence occurs.
- Present Security_Rejection_Nonce as a Voucher that administrators can cross-check against physical or exported logs.
- Auto-pop a red alert in under 500ms after deploy/api receives Security_Rejection_Nonce, using Server-Sent Events (SSE) or WebSocket rather than manual refresh.
- Consume deploy/api through backend-owned APIs rather than reading cloud durable storage directly.

### Out Of Scope
- Owning edge runtime behavior.
- Owning cloud-side shadow-state comparison logic.
- Serving as an ingress path for edge-to-cloud traffic.

### Dependency Direction
- deploy/web depends on deploy/api for state and operator actions.
- src/qwenpaw/security must not call deploy/web; edge access is frozen to deploy/api over HTTP.
- This boundary must not become a hidden control plane that bypasses the backend API.

### Required UI Roles
- anomaly dashboard
- rejected-event evidence view
- trust-state and UNTRUSTED recovery view
- trust-state, lease-expiry downgrade, and UNTRUSTED recovery view
- recovery-handshake progress view
- hash-break curve chart with explicit fork point marker
- nonce Voucher display for Security_Rejection_Nonce verification
- realtime red-alert popup driven by deploy/api SSE or WebSocket push

### Notes
- Coding/Repair may choose concrete frontend stack and asset pipeline, but must keep the operator web separate from the edge runtime, route all state reads and actions through deploy/api, and forbid operator polling or manual refresh as the primary path for Security_Rejection_Nonce alert visibility.
