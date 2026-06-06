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
- Freeze runtime-inspection expectations for `sec-e2e-024`, `sec-e2e-025`, `sec-e2e-027`, and `sec-e2e-021`: tool-boundary context spying, direct physical ledger inspection, local hash-chain verification, checkpoint-loss-as-tamper handling with readable `UNTRUSTED` state, lease-expiry-driven `UNTRUSTED` downgrade plus reconnect gating, durable rejected-event evidence with trace-bound nonce semantics, and pre-execution evidence ordering.
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
  control_point: drive a sensitive action, tamper with the local audit artifact by operating-system means, then attempt resumed sensitive work through the real app subprocess
  observation_point: the resulting observations prove or disprove one business-level continuity anomaly, checkpoint loss treated as tamper, explicit `UNTRUSTED` state, refusal of resumed sensitive tooling, explicit recovery visibility through both the frozen Security Center backend API and the frozen Security Center operator web, and a hash-break curve chart with a visually marked fork point between local and cloud shadow hashes
- testcase_name: sec-e2e-027-lease-expiry-active-defense
  entry_path: test_audit_foundation.py::test_lease_expiry_blocks_untrusted_rejoin_until_gap_sync
  control_point: let a previously trusted device session miss its lease heartbeat window, then attempt to resume model access through the real app subprocess before missing-gap verification completes
  observation_point: the resulting observations prove or disprove lease-heartbeat projection, Security Center `UNTRUSTED` downgrade, reconnect denial at model-access scope, readable missing-gap verification requirements, operator web recovery visibility, and post-recovery access restoration only after continuity is proven
- testcase_name: sec-e2e-021-prompt-injection-tool-guard-enforced
  entry_path: test_audit_foundation.py::test_prompt_injection_cannot_bypass_high_risk_tool_guard
  control_point: submit deceptive nested instructions that claim test mode or maintenance mode while targeting a configured High risk tool without trusted provenance or confirmation
  observation_point: the resulting observations prove or disprove tool-call-boundary interception, missing-trust rejection with a non-static Security_Rejection_Nonce bound to the current trace chain, durable rejected-event evidence, visible nonce Voucher presentation in the frozen Security Center operator web, and a red alert pushed from deploy/api over SSE or WebSocket to the operator web in under 500ms without manual refresh

### Protected Fixtures
- harness.py

### Notes
- The testcase body in `test_audit_foundation.py` is frozen as a business contract baseline. Coding/Repair may realize runtime behavior underneath the harness, but should not rewrite the business wording, GIVEN/WHEN/THEN structure, or explicit entrypoint paths without an upstream architecture change.
- In the current repository state, the harness is expected to fail with business-readable `Non_Repudiation_Gap`, `Audit_Integrity_Lockdown_Gap`, `Lease_Expiry_Active_Defense_Gap`, and `Prompt_Injection_Guard_Gap` categories because the live runtime still lacks the required tool-boundary probes, durable ledger semantics, readable lock-mode or lease-expiry surfacing, recovery handshake evidence, lease heartbeat projection, reconnect gating, and durable rejected-event projection with Security_Rejection_Nonce semantics.
- When the shared real-environment bootstrap itself is incomplete, the explicit entrypoint must still fail inside the testcase body with a readable runtime bootstrap blocker rather than disappearing behind fixture setup noise.
