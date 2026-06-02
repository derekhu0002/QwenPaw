---
contract_type: implementation-architecture-element
contract_version: 1
scope: stable-element
element_name: qwenpaw-operator-cli
element_kind: OperatorCli
element_path: src/qwenpaw/cli
---

## Implementation Architecture Contract

### Responsibility
- Own the click-based local operator command surface exposed through the qwenpaw entrypoint.
- Keep command discovery rooted in main.py with lazy subcommand loading for bounded startup cost.
- Delegate business behavior to runtime helpers instead of embedding backend orchestration inside the CLI shell.

### Out Of Scope
- Owning HTTP router behavior under src/qwenpaw/app.
- Owning frontend operator UX under console/.

### Stable Files
- path: main.py
  role: root click group and lazy command registration surface
- path: agents_cmd.py
  role: multi-agent operator command family
- path: task_cmd.py
  role: headless task execution command family

### Explicit Testcase Entrypoints
- tests/unit/cli/test_cli_version.py::test_cli_version_option_outputs_current_version
- tests/unit/cli/test_cli_agents.py::test_agents_list_uses_shared_tool_helper
- tests/unit/cli/test_cli_task.py::test_task_command_registered_in_cli

### Notes
- The current repository state keeps command modules mostly flat under this directory, while startup cost is constrained by LazyGroup-based deferred imports in main.py.