---
contract_type: implementation-architecture-element
contract_version: 1
scope: stable-element
element_name: qwenpaw-console
element_kind: OperatorConsole
element_path: console
---

## Implementation Architecture Contract

### Responsibility
- Own the operator-facing console frontend and Tauri-oriented packaging assets.
- Materialize pages, hooks, stores, layouts, and API client code for the browser or desktop console surface.

### Out Of Scope
- Owning Python backend runtime behavior.
- Owning public documentation and marketing content under website/.

### Stable Subdirectories
- src/api
- src/pages
- src/layouts
- src/stores
- src/tauri

### Dependency Direction
- The console depends on backend APIs and shared runtime contracts, but the runtime must not depend on console implementation details.---
contract_type: implementation-architecture-element
contract_version: 1
scope: stable-element
element_name: qwenpaw-console
element_kind: OperatorConsole
element_path: console
---

## Implementation Architecture Contract

### Responsibility
- Own the operator-facing browser console and bundled Tauri-specific frontend assets.
- Materialize runtime administration, chat, settings, channel, and coding-mode UI flows against backend APIs.

### Out Of Scope
- Owning backend API behavior or CLI entrypoints.
- Owning external documentation and adoption content.

### Children
- path: src
  kind: frontend-source
  role: React application source for operator workflows
- path: src-tauri
  kind: desktop-shell
  role: Tauri bootstrap and desktop packaging assets
- path: public
  kind: static-assets
  role: static assets served with the console bundle

### Notes
- No explicit testcase is mounted here yet in the intent graph. The current acceptance baseline is backend and CLI centered, while console behavior remains covered by implementation-side tests and future design expansion.

## Integrity Protection Delivery Addendum

### Responsibility
- Own the Settings/Security Integrity Check submenu and Health Check submenu that serve `intent-integrity-security-console`.
- Keep Integrity Check and Health Check visually and navigationally peer-level with Tool Guard and File Guard.
- Present operator-visible switches, protected-path lists, rule-integrity status, health-check progress, risk summaries, Restore, Accept, and confirmed-fix actions.
- Localize every Integrity Check and Health Check operator-visible string through the existing `console/src/i18n.ts` mechanism for English and Simplified Chinese, with English fallback for other configured languages.
- Show a Health Check scan progress carousel that rotates localized current-check text while scanning and stops on completion, failure, cancellation, or interruption without running a fix.
- Project Health Check scan and final results from backend structured doctor coverage items rather than a hardcoded two-item list.
- Display doctor groups, check item ids, status, detail, risk or recommendation, and mapped fix affordance when present. Default scan must remain local/read-only; deep connectivity checks require an explicit advanced scan option.

### Out Of Scope
- Owning persona baseline, source trust, doctor scan/fix, or rule-integrity backend semantics.
- Running package installation, package execution, file restoration, baseline acceptance, rule repair, or doctor fix without an explicit backend action initiated by the user.

### Dependency Direction
- `console/src/api/modules/security.ts` is the stable client module for security settings and Integrity Protection API calls.
- Console components may call backend APIs and display state, but must not import Python runtime code, parse `qwenpaw doctor` CLI text, or duplicate doctor/ClawSec verification logic.

### Explicit Testcase Entrypoints
- ../tests/integration/security/test_integrity_protection.py::test_integrity_security_menu_default_off
- ../tests/integration/security/test_integrity_protection.py::test_persona_drift_alert_restore_accept
- ../tests/integration/security/test_integrity_protection.py::test_health_check_scan_and_confirmed_fix
- ../tests/integration/security/test_integrity_protection.py::test_rule_integrity_entry_visible
- ../tests/integration/security/test_integrity_protection.py::test_security_i18n_and_healthcheck_progress_carousel
- ../tests/integration/security/test_integrity_protection.py::test_healthcheck_full_doctor_coverage_projection

### Current Evidence
- Current repository evidence confirms `console/src/api/modules/security.ts` already covers Tool Guard, File Guard, Skill Scanner, and built-in rules-integrity APIs.
- Current repository evidence confirms `console/src/api/modules/security.ts`, `console/src/pages/Settings/Security/components/IntegrityCheckSection.tsx`, and `console/src/pages/Settings/Security/components/HealthCheckSection.tsx` now carry Integrity Check and Health Check API client calls, persona drift actions, passive rule integrity check, read-only health scan, and second-confirmed fix controls. Source trust UI was removed (deferred).
- Current repository evidence confirms Integrity Check and Health Check copy is still hardcoded in `console/src/pages/Settings/Security/index.tsx`, `console/src/pages/Settings/Security/components/IntegrityCheckSection.tsx`, and `console/src/pages/Settings/Security/components/HealthCheckSection.tsx`; `tests/integration/security/test_integrity_protection.py::test_security_i18n_and_healthcheck_progress_carousel` is expected to fail until Coding/Repair replaces this copy with i18n keys and implements the localized current-check carousel.
- Current repository evidence confirms `HealthCheckSection.tsx` still falls back to `DEFAULT_SCAN_ITEM_IDS = ["working-dir", "console-static-build"]` and `console/src/locales/en.json` plus `console/src/locales/zh.json` only define those two scan item labels. `tests/integration/security/test_integrity_protection.py::test_healthcheck_full_doctor_coverage_projection` is expected to fail until Coding/Repair adds grouped full doctor coverage rendering, deep scan control, and locale keys for every required group and scan item.