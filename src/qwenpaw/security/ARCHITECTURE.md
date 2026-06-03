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
- Freeze the seam where request or channel metadata becomes trusted `SecurityContext` provenance, where high-risk approvals become durable confirmation evidence, and where local audit records become queryable evidence chains for `sec-e2e-024`.
- Provide the business-facing projection contract that a local or remote Security Center can consume without requiring explicit testcase bodies to reach into transport plumbing.
- Expose enough runtime inspection shape for the explicit testcase to verify implicit context propagation at the tool boundary, direct disk-level confirmation evidence, hash-chain continuity, and the order 'store evidence before executing the high-risk tool effect' against the real `app_server` subprocess and its isolated working directory.

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
  - Coding/Repair must replace heartbeat-oriented traces with canonical audit events, continuity binding, evidence-chain reconstruction, and disk-level USER_CONFIRMATION inspection exposed through this contract and queryable from the live runtime.
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

### Critical Non-Explicit Tests
- ../../tests/architecture/security-audit-contract-boundaries.test.js
- ../../tests/architecture/security-explicit-entrypoint-traceability.test.js

### Current Evidence And Gaps
- Current repository evidence confirms contextvars-based transport identity in `../app/agent_context.py`.
- Current repository evidence confirms high-risk approval routing in `../app/approvals/service.py`, but the record is still in-memory and does not yet expose a durable confirmation digest.
- Current repository evidence confirms append-only trace writing in `../app/inbox_trace_store.py`, but it does not yet expose canonical audit events, evidence-chain reconstruction, or a Security Center query surface.
- The live integration runtime still does not show a tool-boundary runtime spy, a direct disk-level USER_CONFIRMATION record, a local hash-chain verifier, or an enforced pre-execution evidence write order.
- Coding/Repair must close those gaps behind this owning contract rather than pushing security semantics back into `app/` or test bodies.
