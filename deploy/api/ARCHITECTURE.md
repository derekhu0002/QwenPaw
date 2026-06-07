---
contract_type: implementation-architecture-element
contract_version: 1
scope: stable-element
element_name: security-center-backend-api
element_kind: SecurityCenterBackendApi
element_path: deploy/api
---

## Implementation Architecture Contract

### Responsibility
- Own the backend HTTP API service for Security Center.
- Receive edge-side uplinks from src/qwenpaw/security through repository-owned HTTP endpoints only.
- Expose operator-facing query APIs for anomaly state, rejected-event evidence, recovery-handshake status, and shadow-hash continuity.
- Expose operator-facing query APIs for anomaly state, lease expiry and trust state, rejected-event evidence, recovery-handshake status, and shadow-hash continuity.
- Expose a realtime operator push channel over Server-Sent Events (SSE) or WebSocket for Security_Rejection_Nonce receipt, hash-divergence updates, and trust-state escalation.
- Own cloud-side shadow-state comparison, rejected-event intake, and recovery-handshake orchestration.
- Own cloud-side lease registry, TTL-expiry downgrade decisions, shadow-state comparison, rejected-event intake, and recovery-handshake orchestration.

### Out Of Scope
- Owning edge runtime behavior or local audit files.
- Rendering operator UI directly.
- Exposing non-HTTP transports to the edge runtime for this slice.

### Dependency Direction
- src/qwenpaw/security may call this boundary only through HTTP.
- deploy/web may consume this boundary's APIs for visualization and operator workflows.
- deploy/web may consume this boundary's SSE or WebSocket push stream for red-alert popups and shadow-hash divergence updates.
- This boundary must not read edge-local files, share edge durable storage, or be imported into the edge runtime as a library.

### Required API Roles
- audit uplink intake API
- rejected-event evidence API
- recovery-handshake API
- operator query API for anomaly and trust state
- operator query API for anomaly, lease expiry, and trust state
- shadow-hash divergence timeline API that returns local-hash and cloud-shadow-hash curve series plus the fork point marker
- nonce voucher API surface that exposes Security_Rejection_Nonce as a human-verifiable operator artifact
- realtime operator alert stream over Server-Sent Events (SSE) or WebSocket

### Notes
- Coding/Repair may choose concrete framework and route layout, but must preserve HTTP as the edge transport, keep this backend as the only cloud-side control point for edge interactions, require missing-gap verification before an `UNTRUSTED` client regains model access, and publish Security_Rejection_Nonce-triggered operator alerts to deploy/web in under 500ms from uplink receipt without requiring manual refresh.
- The lease registry and recovery model are keyed by one canonical runtime client id per live edge runtime. A startup heartbeat must not create a separate bootstrap-only client whose shadow hash is later compared against the real audit chain for that same runtime.
- Current repository evidence still proves the backend can project lease timing through operator query surfaces and keeps recovery gated until cloud-side gap validation succeeds, but the latest intent handoff now reopens sec-e2e-027 on a different seam: a freshly started online runtime can still be projected as `GAP_VALIDATION_REQUIRED` with `gap_status=REQUIRED`, `recovery_gate_status=OPEN`, and `divergence_reason=missing_gap_proof` before any offline lease-expiry event has occurred.
- Current repository evidence also proves the explicit-gap-verification shortcut no longer returns clients to `ALIGNED` without an accepted full-chain gap proof.
- The supporting contract test at `../../tests/contract/security/test_lease_recovery_semantics_contract.py` now guards those semantics as passing regression tests: one for TTL-driven lease downgrade and one for rejecting hash-only recovery shortcuts without full-chain cloud validation.
- A newer supporting contract in that same file now passes as a regression guard: runtime startup registers a lease client before user prompt traffic begins, so the product background Heartbeat Emitter requirement from the updated intent handoff is now closed and deploy/api continues to project lease timing as soon as heartbeats arrive.
- The critical architecture guard at `../../tests/architecture/security-runtime-client-identity-boundary.test.js` still passes, but it is only a static boundary guard.
- The live supporting guard at `../../tests/contract/security/test_lease_recovery_semantics_contract.py::test_security_center_projects_one_online_runtime_as_one_canonical_terminal` now currently passes as a behavior-level regression guard: after startup heartbeat plus one session-scoped security flow, deploy/api continues to report one canonical terminal for one live runtime while allowing session ids only as aliases or metadata.
- The supporting guard at `../../tests/contract/security/test_lease_recovery_semantics_contract.py::test_security_center_persists_runtime_lease_fields_and_downgrades_after_stop` now passes and remains frozen as regression protection for durable lease timing plus post-stop TTL downgrade.
- The critical architecture guard at `../../tests/architecture/security-runtime-lease-persistence-boundary.test.js` now passes and remains frozen as regression protection for the API/store lease-persistence seam.
- The new supporting guard at `../../tests/contract/security/test_lease_recovery_semantics_contract.py::test_security_center_projects_fresh_runtime_startup_as_aligned_clear_terminal` is now frozen as the reopened sec-e2e-027 delivery gate. Control point: start API, web, and runtime from a fresh bootstrap, then observe Security Center before any intentional runtime stop, offline lease-expiry demonstration, or session-scoped recovery workflow. Observation point: overview and timeline must show one canonical startup terminal with nonzero durable lease fields, `trust_state=ALIGNED`, `gap_status=CLEAR`, `recovery_gate_status=CLEAR`, `recovery_required=false`, and no `missing_gap_proof` or other startup divergence reason. Current repository state is expected to fail this guard until Coding/Repair stops treating a clean startup heartbeat as a recovery-gated missing-gap attempt.
- Live acceptance must begin from a reset demo state and restarted processes. Before operator-side overview validation, run `scripts/reset-showcase-demo-state.ps1`, then restart Security Center API, Security Center web, and the QwenPaw runtime so stale store contents or stale processes cannot fabricate extra terminals or stale divergence state.
- deploy/api must preserve that repaired single-terminal model and bootstrap alignment so a live non-forked runtime does not regress to `DIVERGED` with `recovery_gate_status=OPEN` on `local_hash_mismatch` alone.
- deploy/api must also preserve `lease_ttl_seconds` on the recovery-handshake HTTP contract and durably write `last_heartbeat_at`, `lease_ttl_seconds`, and `lease_expires_at` for the canonical runtime client before operator queries observe lease timing. Read-model projection from `updated_at_ns` is not an acceptable substitute for this contract.
- deploy/api must also admit a clean startup heartbeat for the canonical runtime terminal as normal online state. Unless a real expired lease, fork, tamper event, or validated missing continuity gap already exists, startup heartbeat must converge to `trust_state=ALIGNED`, `gap_status=CLEAR`, `recovery_gate_status=CLEAR`, and `recovery_required=false` rather than `GAP_VALIDATION_REQUIRED` with `missing_gap_proof`.
