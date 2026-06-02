# Overall Implementation Architecture

## Scope
- Define the stable implementation elements that currently realize QwenPaw in this repository.
- Anchor current-state implementation boundaries for backend runtime, CLI, console, website, test ownership, and validator assets.
- Materialize the current explicit testcase entrypoints already present in the repository without inventing new product scope.

## Stable Elements
- path: src/qwenpaw
  kind: RuntimeRoot
  implements:
    - intent-backend-runtime
  contract: src/qwenpaw/ARCHITECTURE.md
  role: Python runtime root that owns API routers, agents, channels, config, security, providers, and shared utilities.

- path: src/qwenpaw/cli
  kind: OperatorCli
  implements:
    - intent-local-operator-cli
  contract: src/qwenpaw/cli/ARCHITECTURE.md
  role: Local operator command surface mounted under the qwenpaw entrypoint.

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
  role: Physical owner of explicit testcase entrypoints and architecture guardrail tests.

- path: .github/validator
  kind: BootstrapAssetZone
  implements:
    - intent-architecture-validator
  contract: .github/validator/ARCHITECTURE.md
  role: Schema and handoff validator scripts invoked by repository-native npm validation commands.

## Dependency Direction
- src/qwenpaw/cli depends inward on stable runtime/config surfaces in src/qwenpaw and does not own backend orchestration state.
- console and website consume runtime-facing APIs and static assets but runtime code does not depend on frontend implementation details.
- tests depend on stable implementation interfaces and contracts; production code must not depend on tests.
- .github/validator validates design assets and handoffs but does not own product behavior.

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

## Critical Non-Explicit Guardrails
- tests/architecture/root-architecture-contracts.test.js guards the presence and traceability of the current root architecture deliverables.
- tests/architecture/validator-bootstrap-traceability.test.js guards the wiring between package.json validation commands and bundled validator assets.

## Frozen Files For Downstream Coding
- design/KG/SystemArchitecture.json
- design/KG/IntentToImplementationHandoff.json
- design/KG/ImplementationToCodingHandoff.json
- OVERALL_ARCHITECTURE.md
- src/qwenpaw/ARCHITECTURE.md
- src/qwenpaw/cli/ARCHITECTURE.md
- console/ARCHITECTURE.md
- website/ARCHITECTURE.md
- tests/ARCHITECTURE.md
- .github/validator/ARCHITECTURE.md# Overall Architecture

## Scope

This contract defines the stable implementation architecture elements that realize the current QwenPaw repository. It is derived from the present repository layout and existing executable entrypoints rather than from a separate external design source.

## Stable Elements

- `src/qwenpaw`
  - Owns the Python product runtime, including API routers, agent runtime, channel orchestration, configuration, providers, security, and the packaged CLI surface.
  - Implements intent elements `intent-backend-runtime` and `intent-operator-cli`.
- `console`
  - Owns the operator-facing web console and bundled Tauri shell assets.
  - Implements intent element `intent-console-surface`.
- `website`
  - Owns the external documentation and adoption-facing website.
  - Implements intent element `intent-adoption-website`.
- `tests`
  - Owns explicit testcase entrypoints and implementation-side verification assets.
  - Implements repository verification ownership for the runtime, CLI surface, and architecture guardrails.
- `.github/validator`
  - Owns schema and stage-handoff validation shims exposed by the root npm scripts.
  - Implements intent element `intent-architecture-validator`.

## Dependency Direction

- `console` and `website` may depend on backend contracts and assets, but backend runtime code must not depend on frontend implementation details.
- `tests` may observe all stable elements but must not become a hidden execution dependency of product runtime modules.
- `.github/validator` constrains architecture artifact validity and explicit testcase execution wiring; business runtime code does not depend on validator internals.

## Test Ownership

- Explicit acceptance entrypoints are currently mounted in existing lightweight pytest cases under `tests/unit/cli` and `tests/unit/routers`.
- Critical non-explicit architecture guardrails live under `tests/architecture` and protect the presence and traceability of architecture deliverables and validator shims.
- Stable local contracts are:
  - `src/qwenpaw/ARCHITECTURE.md`
  - `console/ARCHITECTURE.md`
  - `website/ARCHITECTURE.md`
  - `tests/ARCHITECTURE.md`
  - `tests/architecture/ARCHITECTURE.md`
  - `.github/validator/ARCHITECTURE.md`

## Current Boundaries

- The Python runtime in `src/qwenpaw` is the single stable backend execution surface for API, agent, channel, and CLI behavior.
- `console` is the stable operator UI boundary.
- `website` is the stable external-facing content boundary.
- Architecture validation is routed through root npm scripts and implemented by `.github/validator/script`.