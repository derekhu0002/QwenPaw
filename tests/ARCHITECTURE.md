---
contract_type: implementation-architecture-element
contract_version: 1
scope: stable-element
element_name: qwenpaw-verification-suite
element_kind: VerificationSuite
element_path: tests
---

## Implementation Architecture Contract

### Responsibility
- Own the physical repository entrypoints for explicit and non-explicit verification assets.
- Keep architecture guardrails under `tests/architecture` and product behavior tests under `unit/`, `integration/`, `contract/`, and `e2e/`.
- Keep explicit security acceptance bodies business-readable by routing low-level inspection through harness helpers inside `tests/integration/security`.

### Out Of Scope
- Defining acceptance scope independently from `design/KG/SystemArchitecture.json`.
- Owning production code or runtime bootstrap logic.

### Children
- path: unit
  kind: explicit-entrypoint-zone
  role: lightweight pytest entrypoints used as the current CLI and backend explicit testcase baselines
- path: architecture
  kind: architecture-guard-zone
  role: critical non-explicit tests protecting architecture deliverables, validator wiring, and security-entrypoint traceability
- path: integration/security
  kind: explicit-entrypoint-zone
  role: business-readable security acceptance entrypoints and protected harness helpers
- path: integration
  kind: supporting-verification-zone
  role: integration-level regression coverage owned by implementation
- path: e2e
  kind: supporting-verification-zone
  role: end-to-end behavior coverage beyond the current explicit baseline

### Explicit Testcase Entrypoints
- unit/cli/test_cli_version.py::test_cli_version_option_outputs_current_version
- unit/cli/test_cli_agents.py::test_agents_list_uses_shared_tool_helper
- unit/cli/test_cli_task.py::test_task_command_registered_in_cli
- unit/routers/test_settings.py::test_put_then_get_roundtrip
- unit/routers/test_git.py::test_git_helper_uses_shared_command_runner
- integration/security/test_audit_foundation.py::test_end_to_end_non_repudiation_evidence_chain

### Critical Non-Explicit Tests
- architecture/root-architecture-contracts.test.js
- architecture/root-architecture-deliverables.test.js
- architecture/validator-bootstrap-traceability.test.js
- architecture/security-audit-contract-boundaries.test.js
- architecture/security-explicit-entrypoint-traceability.test.js

### Supporting Non-Explicit Tests
- integration/test_security_config.py

### Protected Fixtures
- integration/security/harness.py

### Notes
- The current explicit testcases are intentionally anchored to repository-owned pytest entrypoints so the architecture baseline stays executable in the current workspace state.
- `tests/integration/security/harness.py` is a protected fixture for explicit security acceptance bodies. Coding/Repair may realize the runtime behind it, but should not rewrite its business-facing vocabulary, runtime-inspection method names, or the read-only testcase entrypoint without an upstream architecture change.
