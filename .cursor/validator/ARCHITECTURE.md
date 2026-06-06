---
contract_type: implementation-architecture-element
contract_version: 1
scope: stable-element
element_name: bundled-validator-assets
element_kind: BootstrapAssetZone
element_path: .cursor/validator
---

## Implementation Architecture Contract

### Responsibility
- Store the bundled validator assets that Argo init/bootstrap projects into Cursor-managed workspace paths.
- Keep validator implementation assets separated from target-workspace business directories while still allowing Cursor MCP tools to invoke them in place.

### Out Of Scope
- Owning target-workspace package.json mutation logic.
- Owning business-facing backend, console, or website behavior.

### Children
- path: script/validateStageHandoff.js
  kind: bundled-validator-script
  role: bundled handoff validator executable copied into managed .cursor workspace paths
- path: script/validateSystemArchitecture.js
  kind: bundled-validator-script
  role: bundled SystemArchitecture schema validator executable copied into managed .cursor workspace paths
- path: script/runArchitectureTests.js
  kind: bundled-validator-script
  role: bundled explicit testcase execution script copied into managed .cursor workspace paths for MCP/agent invocation

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
    - ../../package.json
  rationale: keep validator assets traceable to the bootstrap contract and npm manifest shim
  frozen_by_stage: implementationdesign

### Notes
- Cursor agents invoke these scripts through the `argo-validator` MCP server defined in `.cursor/mcp.json`.
- MCP entrypoint: `.cursor/tools/validator/server.js`
- MCP tools:
  - `validateSystemArchitecture`
  - `validateStageHandoff`
  - `runArchitectureTests`
- Schema assets live under `.cursor/argoschema/`.
