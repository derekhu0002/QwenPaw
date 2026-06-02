---
contract_type: implementation-architecture-element
contract_version: 1
scope: stable-element
element_name: bundled-validator-assets
element_kind: BootstrapAssetZone
element_path: .github/validator
---

## Implementation Architecture Contract

### Responsibility
- Store the bundled validator assets that /argo-init projects into Argo-managed workspace paths.
- Keep validator implementation assets separated from target-workspace business directories while still allowing bootstrap to copy them.

### Out Of Scope
- Acting as the repository-level invocation shim for npm scripts.
- Owning target workspace package.json mutation logic.

### Children
- path: script/validateStageHandoff.js
  kind: bundled-validator-script
  role: bundled handoff validator executable copied into managed .github workspace paths
- path: script/validateSystemArchitecture.js
  kind: bundled-validator-script
  role: bundled SystemArchitecture schema validator executable copied into managed .github workspace paths
- path: script/runArchitectureTests.js
  kind: bundled-validator-script
  role: bundled explicit testcase execution script copied into managed .github workspace paths for npm/agent invocation

### Test Guardrails
#### critical_non_explicit_tests
- test_id: validator-bootstrap-traceability
  critical_kind: implementation-traceability
  test_path: ../../tests/architecture/validator-bootstrap-traceability.test.js
  execution_entry: ../../tests/architecture/validator-bootstrap-traceability.test.js
  guards_elements:
    - script/validateStageHandoff.js
    - script/validateSystemArchitecture.js
    - script/runArchitectureTests.js
  protected_baselines:
    - ARCHITECTURE.md
  rationale: keep validator assets traceable to the bootstrap contract and npm manifest shim
  frozen_by_stage: implementationdesign

### Notes
- The repository-level shims remain at ../../scripts/validateStageHandoff.js, ../../scripts/validateSystemArchitecture.js, and ../../scripts/runArchitectureTests.js so package.json can expose stable invocation paths without moving the bundled assets.
