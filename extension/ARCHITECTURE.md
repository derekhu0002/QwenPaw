---
contract_type: implementation-architecture-element
contract_version: 1
scope: stable-element
element_name: qwenpaw-extension-adapters
element_kind: ExtensionAdapterZone
element_path: extension
---

## Implementation Architecture Contract

### Responsibility
- Own PRD-scoped extension design notes and low-intrusion adapters for optional security deliveries.
- Keep Integrity Protection Delivery adapters decoupled from core runtime internals while integrating through stable `src/qwenpaw/security`, `src/qwenpaw/app`, `src/qwenpaw/cli`, and `console` contracts.
- Treat `extension/Intergrity  Protection PRD.txt` as business evidence and `extension/Intergrity  Protection Design.md` as the implementation-stage adapter design for this slice.

### Out Of Scope
- Owning backend router composition, runtime security semantics, or console rendering.
- Duplicating ClawSec soul-guardian, ClawSec guarded skill install, qwenpaw doctor, or built-in rule integrity behavior.
- Storing production signing private keys. The PRD plaintext private-key tool is limited to local/demo signing until a separate production key-management decision is made.
- Owning console i18n implementation details or Health Check carousel rendering mechanics; those remain under the `console` contract and are only constrained here by the PRD-scoped Integrity Protection intent.
- Owning doctor check semantics or parsing doctor CLI text; full coverage projection must reuse stable doctor helpers through the runtime/security boundary.

### Children
- path: Intergrity  Protection PRD.txt
  kind: business-prd-evidence
  role: user-provided integrity-protection requirements for persona drift, source trust, health check, rule integrity, and console placement
- path: Intergrity  Protection Design.md
  kind: implementation-design-contract
  role: adapter-level implementation design and Coding/Repair constraints for Integrity Protection Delivery
- path: persona_baseline/
  kind: extension-module
  role: persona drift protection business logic and host_bridge wiring for inbox/push/SSE
- path: health_check/
  kind: extension-module
  role: doctor-derived Health Check projection (projection.py), scan orchestration (scanner.py), confirmed fix (fix.py)
- path: rule_integrity/
  kind: extension-module
  role: built-in tool guard rule integrity verify/repair, API routes, startup polling, and acceptance harness/tests
- path: Console Frontend Decoupling Design.md
  kind: implementation-design-contract
  role: console/src/extension module layout and re-export boundary

### Dependency Direction
- `extension` adapters may depend inward on stable QwenPaw backend, CLI, console API, and thirdparty ClawSec capabilities.
- `src/qwenpaw/security` and `console` must not depend on incidental extension implementation details that are not promoted through explicit backend or API contracts.
- Verification assets under `tests/integration/security` observe Integrity Protection through harness abstractions, not by importing extension adapter internals directly.

### Explicit Testcase Entrypoints
- tests/integration/security/test_integrity_protection.py::test_integrity_security_menu_default_off
- tests/integration/security/test_integrity_protection.py::test_persona_drift_alert_restore_accept
- tests/integration/security/test_integrity_protection.py::test_health_check_scan_and_confirmed_fix
- extension/rule_integrity/tests/test_integration_entry.py::test_rule_integrity_entry_visible
- tests/integration/security/test_integrity_protection.py::test_security_i18n_and_healthcheck_progress_carousel
- tests/integration/security/test_integrity_protection.py::test_healthcheck_full_doctor_coverage_projection

### Current Evidence
- Current repository evidence confirms the PRD path, existing reusable capabilities, implemented Integrity Protection backend APIs, console submenus, persona drift actions, health-check dashboard, and passive rule-integrity entry. Source trust (PRD section 二) is deferred; prior demo verifier was removed.
- The acceptance entrypoints now pass through production behavior behind `tests/integration/security/integrity_harness.py`; this extension contract must keep the low-intrusion adapter boundary and local/demo signing constraint stable.
- Current repository evidence confirms grouped doctor coverage lives in `extension/health_check/projection.py` with core re-exports from `src/qwenpaw/security/integrity_protection.py`; console UI lives under `console/src/extension/health_check/`.
