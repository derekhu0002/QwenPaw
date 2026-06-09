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
  - Editing any committed audit ledger record is also a red-line tamper signal, including the second non-tail record after three high-risk actions. Coding/Repair must verify the whole committed chain, not only checkpoint presence or the latest tail record, no later than the next high-risk boundary or startup/reconnect preflight.
- shadow-hash divergence projection seam
  - Coding/Repair must project enough divergence metadata to deploy/api and deploy/web so `sec-e2e-025` can render a hash-break curve chart with a visually explicit fork point between the local hash chain and the cloud shadow hash.
- uplink projection seam
  - Coding/Repair must uplink summaries only through the separate `deploy/ARCHITECTURE.md` boundary; explicit testcases may observe cloud-visible evidence only through that seam, never by opening local files from the cloud side.
  - When a Security_Rejection_Nonce is emitted, Coding/Repair must project the nonce as a Voucher plus a realtime red-alert event through deploy/api and deploy/web without requiring operator refresh.
- heartbeat and trust-rejoin seam
  - Coding/Repair must emit repository-owned heartbeat or lease evidence from the edge runtime toward deploy/api so the Security Center can track TTL expiry and downgrade inactive clients to `UNTRUSTED` without moving the lease decision into the edge runtime.
  - Coding/Repair must keep one canonical runtime client id across heartbeat emission, recovery preflight, lockdown projection, and restored-access projection. Browser or session ids may remain audit metadata inside local records, but they must not create separate cloud terminal identities for the same live runtime.
  - Coding/Repair must gate reconnecting model access behind missing-gap verification whenever deploy/api marks the client `UNTRUSTED`; reconnect denial belongs to the backend security boundary, while trust-state projection belongs to the separate Security Center boundary.
  - Coding/Repair must expose a repository-owned recovery control point after denied rejoin so sec-e2e-027 can perform a distinct missing-gap verification step before attempting restored model access; reusing the denied rejoin frame as post-recovery evidence is forbidden.
  - The frozen sec-e2e-027 harness now snapshots `pre_recovery_console_status` and `post_recovery_console_status` separately; runtime changes must preserve those two observation points instead of collapsing denied and restored model access back into one mutable final status.
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
  control_point: drive three high-risk actions through the real app subprocess, edit the second committed non-tail audit record by operating-system means while later records remain present, then attempt another high-risk action without manual trust recovery
  observation_point: the harness must prove a multi-record baseline exists, the second historical record was edited, a historical-record continuity anomaly is detected before the next high-risk boundary, `UNTRUSTED` lock mode is entered, resumed sensitive tooling is refused, both the frozen Security Center backend API plus the frozen Security Center operator web remain recovery-required rather than `CLEAR`, and the operator web renders a hash-break curve chart with an explicit fork point without letting the testcase reach into transport plumbing
- testcase_name: sec-e2e-027-lease-expiry-active-defense
  entry_path: ../../tests/integration/security/test_audit_foundation.py::test_lease_expiry_blocks_untrusted_rejoin_until_gap_sync
  control_point: keep one frozen testcase path but drive two control points through the harness: a denied rejoin before missing-gap verification, followed by a distinct recovery control point and a second restored model-access attempt
  observation_point: the harness must prove a pre-recovery frame where the separate Security Center lease monitor downgrades the client to `UNTRUSTED` and the backend refuses reconnecting model access with a frozen `pre_recovery_console_status`, then a separate post-recovery frame where backend and operator-web trust-state projection update after continuity validation and normal model access is restored with a frozen `post_recovery_console_status`
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
- The live integration runtime still does not show a tool-boundary runtime spy, a direct disk-level USER_CONFIRMATION record, a local hash-chain verifier, a durable rejection event with non-static trace-bound Security_Rejection_Nonce semantics, a hash-break curve chart with explicit fork point, or explicit backend-API and operator-web projections that remain physically separate from the edge runtime.
- Current repository evidence now confirms sec-e2e-027 can hold the denied rejoin frame, advance through the recovery control point, and restore model access while keeping the pre-recovery and post-recovery console observations physically distinct in the frozen harness.
- Current repository evidence now closes the sec-e2e-027 intent semantics beneath the controlled acceptance path: the runtime writes heartbeat evidence that Security Center converts into cloud-side lease timing, the lease monitor can autonomously downgrade expired clients to `UNTRUSTED`, and the recovery path no longer reopens trust through the explicit-gap-verification shortcut without validated gap proof.
- Current repository evidence now also closes the remaining startup-heartbeat gap from the updated intent handoff: runtime startup emits an initial heartbeat automatically through a background Heartbeat Emitter, periodic emission continues while the runtime is alive, and prompt-classified warmup in `../app/routers/console.py` no longer owns product lease registration.
- Current repository evidence now closes the reopened sec-e2e-027 client-identity gap: the live supporting guard at `../../tests/contract/security/test_lease_recovery_semantics_contract.py::test_security_center_projects_one_online_runtime_as_one_canonical_terminal` currently passes, and one online runtime remains projected as one canonical Security Center terminal after startup heartbeat plus later session-scoped security traffic.
- Current repository evidence now also closes the cloud-side lease-persistence seam: the runtime's canonical heartbeat payload carries `lease_ttl_seconds` end-to-end into durable Security Center state, and the stopped-runtime TTL downgrade guard now passes.
- The runtime security boundary must preserve one repository-owned canonical runtime client id across startup heartbeat, recovery preflight, lockdown projection, restored-access projection, and Security Center timeline reads while keeping browser or session ids only as audit metadata or display aliases.
- The runtime security boundary must also preserve the repaired bootstrap-shadow alignment so a live non-forked runtime does not regress to `DIVERGED` with `recovery_gate_status=OPEN` on a mere bootstrap-shadow mismatch once the real audit-chain head advances.
- The runtime security boundary must preserve `lease_ttl_seconds` on canonical runtime heartbeat and recovery payloads so `deploy/api/app.py` and `deploy/api/store.py` can durably persist the same canonical client's `last_heartbeat_at`, `lease_ttl_seconds`, and `lease_expires_at`. Projection-only lease timing is insufficient for sec-e2e-027 delivery.
- Current repository evidence now closes the startup normal-admission seam: a clean canonical startup heartbeat is admitted as a normal online terminal, and fresh startup no longer regresses to `GAP_VALIDATION_REQUIRED` with `gap_status=REQUIRED`, `recovery_gate_status=OPEN`, or `divergence_reason=missing_gap_proof` before any offline lease-expiry event has occurred.
- The runtime security boundary must preserve startup-heartbeat semantics that distinguish a clean online admission from a post-expiry or post-gap recovery attempt. On fresh startup, canonical runtime heartbeat plus current anchor state must admit the terminal as `ALIGNED/CLEAR`; missing-gap recovery must remain reserved for true rejoin after expired lease or verified continuity loss.
- Current repository evidence now also closes the live reconnect recovery seam: the supporting guard at `../../tests/contract/security/test_lease_recovery_semantics_contract.py::test_security_center_live_reconnect_gap_proof_restores_access` now passes against a reset-state API/Web/runtime stack. Control point: establish one trusted canonical client, let it downgrade to `UNTRUSTED` with `divergence_reason=lease_ttl_expired`, restart the same runtime, then attempt restored model access without manual `/security-center/v1/recovery/handshake` proof injection. Observation point: the runtime now materializes a locally constructible full missing-gap proof for the restarted session, automatically posts equivalent recovery evidence, refreshes the same canonical client's lease heartbeat, closes the recovery gate, and stops returning recovery-gated blocking.
- Current repository evidence reopens sec-e2e-025 for historical-record tamper: before this implementation-design pass, the explicit harness drove one high-risk baseline and mutated the latest artifact/checkpoint, so it could not prove that editing the second committed non-tail audit record after three high-risk actions forces `UNTRUSTED` and blocks `CLEAR`. The frozen acceptance entrypoint now physicalizes that missing branch and is expected to fail until Coding/Repair implements whole-ledger verification.
- Coding/Repair must preserve that runtime-owned heartbeat behavior behind this owning contract and `../../deploy/ARCHITECTURE.md` rather than pushing security semantics back into `app/` or test bodies.
