# Overall Implementation Architecture

## Scope
- Freeze the stable implementation boundaries that currently realize QwenPaw in this repository.
- Materialize the `sec-e2e-024`, `sec-e2e-025`, and `sec-e2e-021` explicit acceptance entrypoints as repository-owned, read-only testcase bodies plus their harness abstractions.
- Constrain the explicit security slice to a real-environment acceptance baseline that uses the live app subprocess, real HTTP surfaces, isolated working directories, and a separately contracted cloud-side Security Center boundary.
- Record where intent is already directly implemented, where current code only provides transitional evidence, and which gaps are intentionally handed to Coding/Repair.

## Stable Elements
- path: src/qwenpaw
  kind: RuntimeRoot
  implements:
    - intent-backend-runtime
  contract: src/qwenpaw/ARCHITECTURE.md
  role: Python runtime root that owns backend orchestration, channel/runtime glue, packaged CLI surfaces, and the stable child security boundary.

- path: src/qwenpaw/security
  kind: SecurityAuditFoundation
  implements:
    - intent-local-security-audit-foundation
    - intent-high-risk-tool-guard
  contract: src/qwenpaw/security/ARCHITECTURE.md
  role: Stable backend-owned boundary for trusted security context provenance, high-risk confirmation evidence, local audit-chain semantics, and the local projection/query seam consumed by `sec-e2e-024`.

- path: src/qwenpaw/cli
  kind: OperatorCli
  implements:
    - intent-local-operator-cli
  contract: src/qwenpaw/cli/ARCHITECTURE.md
  role: Local operator command surface mounted under the `qwenpaw` entrypoint.

- path: console
  kind: OperatorConsole
  implements:
    - intent-console-frontend
  contract: console/ARCHITECTURE.md
  role: Browser and desktop-oriented operator console built with Vite, React, and Tauri assets.

- path: website
  kind: DocumentationSite
  implements:
    - intent-docs-website
  contract: website/ARCHITECTURE.md
  role: Public documentation and adoption website.

- path: tests
  kind: VerificationSuite
  contract: tests/ARCHITECTURE.md
  role: Physical owner of explicit testcase entrypoints, business-readable security harnesses, and architecture guardrail tests.

- path: tests/integration/security
  kind: ExplicitSecurityEntrypointZone
  contract: tests/integration/security/ARCHITECTURE.md
  role: Read-only explicit security acceptance entrypoints and harness abstractions whose bodies are written for business readability rather than plumbing detail.

- path: deploy
  kind: SecurityCenterDeploymentBoundary
  implements:
    - intent-security-center
    - intent-cloud-integrity-stub
  contract: deploy/ARCHITECTURE.md
  role: Stable repository-owned contract boundary for the physically separate Security Center service, including a cloud-side HTTP API backend, an operator-facing web frontend, SSE or WebSocket alert delivery to operators, and the integrity mirror seam consumed only through edge-to-cloud HTTP.

- path: .github/validator
  kind: BootstrapAssetZone
  implements:
    - intent-architecture-validator
  contract: .github/validator/ARCHITECTURE.md
  role: Schema and handoff validator scripts invoked by repository-native npm validation commands.

## Dependency Direction
- `src/qwenpaw/app`, channels, and runner glue may capture transport/session metadata, but `src/qwenpaw/security` owns the stable semantics for trusted provenance, confirmation evidence, and audit continuity. Transport layers must not redefine the acceptance boundary for `sec-e2e-024`.
- `src/qwenpaw/security` must not depend on `console` or `website` implementation details.
- `src/qwenpaw/security` may uplink summaries toward the `deploy` boundary, but the cloud-side Security Center must remain a separate process and independent durable store rather than an in-process branch of the edge runtime.
- Edge runtime communication with `deploy` is frozen to repository-owned HTTP APIs only. Coding/Repair must not switch this slice to shared storage, direct database access, or a different transport without a new implementation-architecture change.
- `src/qwenpaw/cli` depends inward on stable runtime and config surfaces in `src/qwenpaw` and does not own backend orchestration state.
- `tests` and `tests/integration/security` may observe all stable elements through declared seams; production code must not depend on test modules.
- `.github/validator` validates design assets and testcase execution wiring but does not own product behavior.

## Intent Realization Mapping
- direct implementation: `src/qwenpaw` realizes `intent-backend-runtime`.
- direct implementation: `src/qwenpaw/security` realizes `intent-local-security-audit-foundation` and its child `intent-high-risk-tool-guard`.
- indirect implementation chain: `src/qwenpaw/app/agent_context.py` provides current contextvars evidence for `intent-implicit-security-context-manager` under the owning `src/qwenpaw/security` contract.
- indirect implementation chain: `src/qwenpaw/app/approvals/service.py` provides current approval-routing evidence that must be converged into durable confirmation evidence under the owning `src/qwenpaw/security` contract.
- indirect implementation chain: `src/qwenpaw/app/inbox_trace_store.py` provides append-only trace evidence that must be converged into canonical audit-chain projection under the owning `src/qwenpaw/security` contract.
- direct architecture boundary materialization: `deploy/ARCHITECTURE.md` realizes the stable repository-owned collaboration contract for `intent-security-center` and `intent-cloud-integrity-stub` while preserving cloud-side process separation from the edge runtime.
- direct sub-boundary materialization: `deploy/api/ARCHITECTURE.md` freezes the Security Center backend HTTP API service consumed by the edge runtime and operator web, including SSE or WebSocket alert publication, nonce voucher APIs, and shadow-hash divergence timeline delivery.
- direct sub-boundary materialization: `deploy/web/ARCHITECTURE.md` freezes the operator-facing Security Center web frontend that visualizes anomalies, rejected events, recovery state, hash-break curve forks, and nonce-driven red alerts.
- direct testcase materialization: `tests/integration/security/test_audit_foundation.py::test_end_to_end_non_repudiation_evidence_chain` is the read-only explicit entrypoint for `sec-e2e-024-end-to-end-non-repudiation-evidence-chain`, and it must run through the real `app_server` fixture rather than repository source inspection.
- direct testcase materialization: `tests/integration/security/test_audit_foundation.py::test_audit_integrity_self_healing_lockdown` is the read-only explicit entrypoint for `sec-e2e-025-audit-integrity-self-healing-lockdown`.
- direct testcase materialization: `tests/integration/security/test_audit_foundation.py::test_prompt_injection_cannot_bypass_high_risk_tool_guard` is the read-only explicit entrypoint for `sec-e2e-021-prompt-injection-tool-guard-enforced`.

## Explicit Testcase Materialization
- testcase: cli-version-surface
  intent_element: intent-local-operator-cli
  entrypoint: tests/unit/cli/test_cli_version.py::test_cli_version_option_outputs_current_version

- testcase: agents-list-surface
  intent_element: intent-local-operator-cli
  entrypoint: tests/unit/cli/test_cli_agents.py::test_agents_list_uses_shared_tool_helper

- testcase: task-help-surface
  intent_element: intent-local-operator-cli
  entrypoint: tests/unit/cli/test_cli_task.py::test_task_command_registered_in_cli

- testcase: settings-language-roundtrip
  intent_element: intent-backend-runtime
  entrypoint: tests/unit/routers/test_settings.py::test_put_then_get_roundtrip

- testcase: git-helper-command-runner
  intent_element: intent-backend-runtime
  entrypoint: tests/unit/routers/test_git.py::test_git_helper_uses_shared_command_runner

- testcase: sec-e2e-024-end-to-end-non-repudiation-evidence-chain
  intent_element: intent-local-security-audit-foundation
  entrypoint: tests/integration/security/test_audit_foundation.py::test_end_to_end_non_repudiation_evidence_chain
  runtime_mode: real-app-subprocess

- testcase: sec-e2e-025-audit-integrity-self-healing-lockdown
  intent_element: intent-local-security-audit-foundation
  entrypoint: tests/integration/security/test_audit_foundation.py::test_audit_integrity_self_healing_lockdown
  runtime_mode: real-app-subprocess

- testcase: sec-e2e-021-prompt-injection-tool-guard-enforced
  intent_element: intent-high-risk-tool-guard
  entrypoint: tests/integration/security/test_audit_foundation.py::test_prompt_injection_cannot_bypass_high_risk_tool_guard
  runtime_mode: real-app-subprocess

## Critical Non-Explicit Guardrails
- tests/architecture/root-architecture-contracts.test.js guards the presence and cross-reference integrity of the root contracts, including the new security contracts.
- tests/architecture/root-architecture-deliverables.test.js guards that the expected architecture deliverables exist at stable repository paths.
- tests/architecture/validator-bootstrap-traceability.test.js guards the wiring between `package.json` validation commands and bundled validator assets.
- tests/architecture/security-audit-contract-boundaries.test.js guards the frozen boundary between `src/qwenpaw/security`, the explicit security entrypoint zone, the separate Security Center deployment boundary, and the root/runtime/test contracts that reference them.
- tests/architecture/security-explicit-entrypoint-traceability.test.js guards that `sec-e2e-024`, `sec-e2e-025`, and `sec-e2e-021` stay mounted to the read-only explicit entrypoints and that the implementation handoff keeps the same paths plus initial failure traceability.

## Frozen Files For Downstream Coding
- design/KG/SystemArchitecture.json
- design/KG/IntentToImplementationHandoff.json
- design/KG/ImplementationToCodingHandoff.json
- design/KG/test-failure-records.json
- OVERALL_ARCHITECTURE.md
- src/qwenpaw/ARCHITECTURE.md
- src/qwenpaw/security/ARCHITECTURE.md
- src/qwenpaw/cli/ARCHITECTURE.md
- console/ARCHITECTURE.md
- website/ARCHITECTURE.md
- deploy/ARCHITECTURE.md
- deploy/api/ARCHITECTURE.md
- deploy/web/ARCHITECTURE.md
- tests/ARCHITECTURE.md
- tests/architecture/ARCHITECTURE.md
- tests/integration/security/ARCHITECTURE.md
- tests/integration/security/harness.py
- tests/integration/security/test_audit_foundation.py
- tests/architecture/root-architecture-contracts.test.js
- tests/architecture/root-architecture-deliverables.test.js
- tests/architecture/security-audit-contract-boundaries.test.js
- tests/architecture/security-explicit-entrypoint-traceability.test.js
- .github/validator/ARCHITECTURE.md
