---
contract_type: implementation-architecture-element
contract_version: 1
scope: stable-element
element_name: security-acceptance-entrypoints
element_kind: ExplicitSecurityEntrypointZone
element_path: tests/integration/security
---

## Implementation Architecture Contract

### Responsibility
- Own the read-only explicit security acceptance entrypoints required by the intent graph for audit-foundation scenarios.
- Keep testcase bodies business-readable and GIVEN/WHEN/THEN-shaped by routing live app-subprocess HTTP, logs, and working-directory inspection through local harness abstractions instead of raw plumbing in the testcase body.
- Freeze runtime-inspection expectations for `sec-e2e-024`, `sec-e2e-025`, `sec-e2e-027`, and `sec-e2e-021`: tool-boundary context spying, direct physical ledger inspection, local hash-chain verification, second committed non-tail audit-record tamper detection with readable `UNTRUSTED` state, lease-expiry-driven `UNTRUSTED` downgrade plus reconnect gating, durable rejected-event evidence with trace-bound nonce semantics, and pre-execution evidence ordering.
- Constrain the explicit security slice to run against the real `app_server` fixture rather than repository source inspection or in-memory-only doubles.

### Out Of Scope
- Owning product runtime behavior under `src/qwenpaw/`.
- Owning root architecture guardrails under `tests/architecture/`.

### Children
- path: harness.py
  kind: protected-explicit-test-fixture
  role: business-readable harness abstraction that drives the real app subprocess, observes runtime HTTP/log/file evidence, reads the physical audit ledger seam, and reports architecture-stage security gaps with business categories
- path: test_audit_foundation.py
  kind: explicit-testcase-entry
  role: single explicit security entrypoint file for audit-foundation scenario baselines

### Explicit Testcase Entrypoints
- testcase_name: sec-e2e-024-end-to-end-non-repudiation-evidence-chain
  entry_path: test_audit_foundation.py::test_end_to_end_non_repudiation_evidence_chain
  control_point: authenticate an employee, request a delegated high-risk action through the real app subprocess, and provide the required confirmation through the harness
  observation_point: the resulting observations prove or disprove tool-boundary implicit context propagation, a complete user -> agent -> plugin -> tool evidence chain, a physical USER_CONFIRMATION audit record on disk inside the isolated working directory, local hash-chain integrity, and the order 'store evidence before releasing the high-risk tool'
- testcase_name: sec-e2e-025-audit-integrity-self-healing-lockdown
  entry_path: test_audit_foundation.py::test_audit_integrity_self_healing_lockdown
  control_point: drive three high-risk actions through the real app subprocess to create a multi-record committed audit baseline, edit the second committed non-tail audit record by operating-system means while leaving later records present, then attempt another high-risk action without manual trust recovery
  observation_point: the resulting observations prove or disprove one business-level continuity anomaly for historical-record tamper, explicit `UNTRUSTED` state, refusal of resumed sensitive tooling, explicit recovery visibility through both the frozen Security Center backend API and the frozen Security Center operator web, no premature `CLEAR` display before cloud-validated full-chain recovery, and a hash-break curve chart with a visually marked fork point between local and cloud shadow hashes
- testcase_name: sec-e2e-027-lease-expiry-active-defense
  entry_path: test_audit_foundation.py::test_lease_expiry_blocks_untrusted_rejoin_until_gap_sync
  control_point: within one frozen explicit entrypoint, first let a previously trusted device session miss its lease heartbeat window and attempt rejoin before missing-gap verification, then drive a second controlled recovery step plus a second model-access attempt after continuity validation
  observation_point: the resulting observations prove or disprove two distinct frames: a pre-recovery frame with lease-heartbeat projection, Security Center `UNTRUSTED` downgrade, denied rejoin at model-access scope, and a frozen `pre_recovery_console_status`; and a post-recovery frame with a distinct recovery control point, distinct backend and operator-web trust-state projection, restored model access only after continuity is proven, and a frozen `post_recovery_console_status`
- testcase_name: sec-e2e-021-prompt-injection-tool-guard-enforced
  entry_path: test_audit_foundation.py::test_prompt_injection_cannot_bypass_high_risk_tool_guard
  control_point: submit deceptive nested instructions that claim test mode or maintenance mode while targeting a configured High risk tool without trusted provenance or confirmation
  observation_point: the resulting observations prove or disprove tool-call-boundary interception, missing-trust rejection with a non-static Security_Rejection_Nonce bound to the current trace chain, durable rejected-event evidence, visible nonce Voucher presentation in the frozen Security Center operator web, and a red alert pushed from deploy/api over SSE or WebSocket to the operator web in under 500ms without manual refresh

### Protected Fixtures
- harness.py

### Notes
- The testcase body in `test_audit_foundation.py` is frozen as a business contract baseline. Coding/Repair may realize runtime behavior underneath the harness, but should not rewrite the business wording, GIVEN/WHEN/THEN structure, or explicit entrypoint paths without an upstream architecture change.
- In the current repository state, the harness is still expected to fail with business-readable `Audit_Integrity_Lockdown_Gap` if the live runtime only detects checkpoint loss or tail truncation and does not detect OS-level editing of the second committed non-tail audit record before the next high-risk boundary.
- sec-e2e-027 is now frozen around two control points and two console observation points inside one explicit entrypoint, and the current repository evidence shows that baseline can execute without sharing one mutable final console status across both frames.
- When the shared real-environment bootstrap itself is incomplete, the explicit entrypoint must still fail inside the testcase body with a readable runtime bootstrap blocker rather than disappearing behind fixture setup noise.
