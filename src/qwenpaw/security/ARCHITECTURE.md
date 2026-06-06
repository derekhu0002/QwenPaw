---
contract_type: implementation-architecture-element
contract_version: 1
scope: stable-element
element_name: local-security-audit-foundation
element_kind: SecurityAuditFoundation
element_path: src/qwenpaw/security
---

## Implementation Architecture Contract

### Responsibility
- Own the stable backend security boundary that directly realizes `intent-local-security-audit-foundation` and `intent-high-risk-tool-guard`.
- Freeze the seam where request or channel metadata becomes trusted `SecurityContext` provenance, where high-risk approvals become durable confirmation evidence, where local audit records become queryable evidence chains for `sec-e2e-024`, where tamper evidence forces lock mode for `sec-e2e-025`, and where tool-boundary rejection remains durable for `sec-e2e-021`.
- Freeze the seam where request or channel metadata becomes trusted `SecurityContext` provenance, where high-risk approvals become durable confirmation evidence, where local audit records become queryable evidence chains for `sec-e2e-024`, where tamper evidence forces lock mode for `sec-e2e-025`, where heartbeat/uplink evidence supports `sec-e2e-027`, and where tool-boundary rejection remains durable for `sec-e2e-021`.
- Provide the business-facing projection contract that a local or remote Security Center can consume without requiring explicit testcase bodies to reach into transport plumbing.
- Expose enough runtime inspection shape for the explicit testcases to verify implicit context propagation at the tool boundary, direct disk-level confirmation evidence, hash-chain continuity, lock mode after tamper evidence, durable rejected-event evidence, and the order 'store evidence before executing the high-risk tool effect' against the real `app_server` subprocess and its isolated working directory.

### Out Of Scope
- Owning FastAPI routing and request transport in `src/qwenpaw/app/`.
- Owning the browser console implementation in `console/`.
- Owning the remote cloud-side Security Center implementation itself.

### Stable Boundaries
- `tool_guard/`
  - Owns tool-call risk evaluation and the enforcement seam for high-risk confirmation before execution continues.
- runtime context inspection seam
  - Coding/Repair must expose a repository-owned probe at the high-risk tool boundary so the explicit testcase can verify, in the live app subprocess, that trusted user identity is read from implicit contextvars rather than from explicit parameter threading.
- `secret_store.py`
  - Owns local secret-protection utilities and remains separate from audit evidence storage.
- approval evidence seam
  - Current repository evidence lives in `../app/approvals/service.py`.
  - Coding/Repair must converge it into durable confirmation artifacts written beneath the isolated runtime working directory without changing the explicit testcase entrypoint.
- context provenance seam
  - Current repository evidence lives in `../app/agent_context.py`.
  - Coding/Repair must keep provenance implicit through contextvars rather than explicit parameter threading.
- audit ledger and projection seam
  - Current repository evidence lives in `../app/inbox_trace_store.py`.
  - Coding/Repair must replace heartbeat-oriented traces with canonical audit events, continuity binding, evidence-chain reconstruction, tamper anomaly projection, rejection-event persistence, and disk-level USER_CONFIRMATION inspection exposed through this contract and queryable from the live runtime.
- lock mode and recovery seam
  - Coding/Repair must expose a repository-owned lock-mode state plus a pre-upload recovery handshake so `sec-e2e-025` can prove that tamper evidence blocks further sensitive tooling until local and cloud anchors reconcile.
  - Physical disappearance of the checkpoint artifact is a red-line tamper signal, not a recoverable cache miss; startup must classify the node as `UNTRUSTED` and force cloud handshake recovery before any resumed sensitive action.
- shadow-hash divergence projection seam
  - Coding/Repair must project enough divergence metadata to deploy/api and deploy/web so `sec-e2e-025` can render a hash-break curve chart with a visually explicit fork point between the local hash chain and the cloud shadow hash.
- uplink projection seam
  - Coding/Repair must uplink summaries only through the separate `deploy/ARCHITECTURE.md` boundary; explicit testcases may observe cloud-visible evidence only through that seam, never by opening local files from the cloud side.
  - When a Security_Rejection_Nonce is emitted, Coding/Repair must project the nonce as a Voucher plus a realtime red-alert event through deploy/api and deploy/web without requiring operator refresh.
- heartbeat and trust-rejoin seam
  - Coding/Repair must emit repository-owned heartbeat or lease evidence from the edge runtime toward deploy/api so the Security Center can track TTL expiry and downgrade inactive clients to `UNTRUSTED` without moving the lease decision into the edge runtime.
  - Coding/Repair must gate reconnecting model access behind missing-gap verification whenever deploy/api marks the client `UNTRUSTED`; reconnect denial belongs to the backend security boundary, while trust-state projection belongs to the separate Security Center boundary.
- pre-execution release seam
  - Coding/Repair must make the confirmation record durable before the high-risk tool effect is released; post-hoc logging is outside the acceptance boundary.

### Dependency Direction
- `src/qwenpaw/security` may consume metadata emitted by `src/qwenpaw/app`, but `app` transport code must not own or redefine the audit-foundation acceptance boundary.
- `tool_guard/` remains the direct enforcement edge for high-risk actions and should feed durable confirmation evidence into this owning element.
- This element must not depend on console implementation details or on test modules.

### Explicit Testcase Entrypoints
- testcase_name: sec-e2e-024-end-to-end-non-repudiation-evidence-chain
  entry_path: ../../tests/integration/security/test_audit_foundation.py::test_end_to_end_non_repudiation_evidence_chain
  control_point: authenticate an employee, delegate a high-risk action through an agent and plugin seam in the real app subprocess, then provide the required confirmation through the security harness
  observation_point: the harness must verify tool-boundary implicit context propagation, reconstruct a business-visible user -> agent -> plugin -> tool chain, read a physical USER_CONFIRMATION record from disk in the isolated working directory, verify hash-chain continuity, and confirm that evidence is written before the high-risk tool effect is released
- testcase_name: sec-e2e-025-audit-integrity-self-healing-lockdown
  entry_path: ../../tests/integration/security/test_audit_foundation.py::test_audit_integrity_self_healing_lockdown
  control_point: drive one sensitive action, tamper with the local audit artifact by operating-system means, then attempt a resumed sensitive action through the real app subprocess
  observation_point: the harness must prove one continuity anomaly, checkpoint loss is treated as tamper, startup enters `UNTRUSTED`, resumed sensitive tooling is refused, both the frozen Security Center backend API plus the frozen Security Center operator web expose the recovery requirement, and the operator web renders a hash-break curve chart with an explicit fork point without letting the testcase reach into transport plumbing
- testcase_name: sec-e2e-027-lease-expiry-active-defense
  entry_path: ../../tests/integration/security/test_audit_foundation.py::test_lease_expiry_blocks_untrusted_rejoin_until_gap_sync
  control_point: allow a previously trusted device session to miss lease heartbeats past the Security Center TTL, then attempt to resume model access through the real app subprocess before missing-gap verification is complete
  observation_point: the harness must prove the separate Security Center lease monitor downgrades the client to `UNTRUSTED`, the backend refuses reconnecting model access before missing-gap verification, the backend API plus operator web expose the recovery requirement, and normal model access is restored only after continuity is validated
- testcase_name: sec-e2e-021-prompt-injection-tool-guard-enforced
  entry_path: ../../tests/integration/security/test_audit_foundation.py::test_prompt_injection_cannot_bypass_high_risk_tool_guard
  control_point: submit deceptive test-mode or maintenance-mode instructions toward a configured High risk tool without trusted provenance or confirmation through the real app subprocess
  observation_point: the harness must prove rejection occurs at the tool-call boundary, the missing trusted context blocks execution with a non-static Security_Rejection_Nonce cryptographically bound to the current trace chain in HTTP response or durable audit evidence, the operator web exposes that nonce as a Voucher, and deploy/api pushes a red alert to the operator web through SSE or WebSocket in under 500ms without manual refresh

### Critical Non-Explicit Tests
- ../../tests/architecture/security-audit-contract-boundaries.test.js
- ../../tests/architecture/security-explicit-entrypoint-traceability.test.js

### Current Evidence And Gaps
- Current repository evidence confirms contextvars-based transport identity in `../app/agent_context.py`.
- Current repository evidence confirms high-risk approval routing in `../app/approvals/service.py`, but the record is still in-memory and does not yet expose a durable confirmation digest.
- Current repository evidence confirms append-only trace writing in `../app/inbox_trace_store.py`, but it does not yet expose canonical audit events, evidence-chain reconstruction, or a Security Center query surface.
- The live integration runtime still does not show a tool-boundary runtime spy, a direct disk-level USER_CONFIRMATION record, a local hash-chain verifier, a readable `UNTRUSTED` state after checkpoint loss or lease expiry, a pre-upload recovery handshake, a durable rejection event with non-static trace-bound Security_Rejection_Nonce semantics, a hash-break curve chart with explicit fork point, or explicit backend-API and operator-web projections that remain physically separate from the edge runtime.
- Coding/Repair must close those gaps behind this owning contract and `../../deploy/ARCHITECTURE.md` rather than pushing security semantics back into `app/` or test bodies.
