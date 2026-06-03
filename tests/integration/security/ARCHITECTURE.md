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
- Freeze runtime-inspection expectations for `sec-e2e-024`: tool-boundary context spying, direct physical ledger inspection, local hash-chain verification, and pre-execution evidence ordering.
- Constrain `sec-e2e-024` to run against the real `app_server` fixture rather than repository source inspection or in-memory-only doubles.

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

### Protected Fixtures
- harness.py

### Notes
- The testcase body in `test_audit_foundation.py` is frozen as a business contract baseline. Coding/Repair may realize runtime behavior underneath the harness, but should not rewrite the business wording, GIVEN/WHEN/THEN structure, or explicit entrypoint path without an upstream architecture change.
- In the current repository state, the harness is expected to fail with a business-readable `Non_Repudiation_Gap` category because the live runtime still lacks a context spy at the high-risk tool boundary, a physical confirmation record with digest and prior-hash, a hash-chain verifier, and an enforced pre-execution evidence write.
- When the shared real-environment bootstrap itself is incomplete, the explicit entrypoint must still fail inside the testcase body with a readable runtime bootstrap blocker rather than disappearing behind fixture setup noise.
