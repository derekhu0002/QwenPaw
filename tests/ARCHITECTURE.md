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
- Keep architecture guardrails under tests/architecture and product behavior tests under unit/, integration/, contract/, and e2e/.

### Out Of Scope
- Defining acceptance scope independently from design/KG/SystemArchitecture.json.
- Owning production code or runtime bootstrap logic.

### Explicit Testcase Entrypoints
- unit/cli/test_cli_version.py::test_cli_version_option_outputs_current_version
- unit/cli/test_cli_agents.py::test_agents_list_uses_shared_tool_helper
- unit/cli/test_cli_task.py::test_task_command_registered_in_cli
- unit/routers/test_settings.py::test_put_then_get_roundtrip
- unit/routers/test_git.py::test_git_helper_uses_shared_command_runner

### Critical Non-Explicit Tests
- architecture/root-architecture-contracts.test.js
- architecture/validator-bootstrap-traceability.test.js---
contract_type: implementation-architecture-element
contract_version: 1
scope: stable-element
element_name: qwenpaw-tests
element_kind: VerificationAssets
element_path: tests
---

## Implementation Architecture Contract

### Responsibility
- Own executable verification assets for runtime, CLI, and architecture guardrails.
- Provide the physical single-entry testcase paths referenced by the intent graph and handoff artifacts.

### Out Of Scope
- Defining business behavior independently from stable runtime contracts.
- Serving as a product runtime dependency.

### Children
- path: unit
  kind: explicit-entrypoint-zone
  role: current lightweight pytest entrypoints used as explicit testcase baselines
- path: architecture
  kind: architecture-guard-zone
  role: critical non-explicit tests protecting validator and architecture-deliverable traceability
- path: integration
  kind: supporting-verification-zone
  role: integration-level regression coverage owned by implementation
- path: e2e
  kind: supporting-verification-zone
  role: end-to-end behavior coverage beyond the current explicit baseline

### Notes
- The current explicit testcases are intentionally anchored to existing lightweight unit/integration-style entrypoints so the architecture baseline stays executable in this repository state.