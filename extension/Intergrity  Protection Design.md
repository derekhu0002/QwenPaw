# Integrity Protection Delivery Implementation Design

## Stable Boundary
- Root delivery slice: `intent-integrity-protection-delivery`.
- Runtime owner: `src/qwenpaw/security/ARCHITECTURE.md`.
- Console owner: `console/ARCHITECTURE.md`.
- Extension adapter owner: `extension/ARCHITECTURE.md`.
- Acceptance owner: `tests/integration/security/ARCHITECTURE.md`.

Integrity Protection is default-off. When disabled, it must not start protected-file monitoring, package verification, doctor scan, doctor fix, rule repair, or any compatibility-affecting startup work.

## Layering
- `extension` owns PRD-scoped adapter design and low-intrusion glue.
- `src/qwenpaw/security` owns integrity-protection backend semantics, including default-off settings, persona baseline lifecycle, source trust verification outcome shape, and rule-integrity exposure.
- `src/qwenpaw/app` owns HTTP/SSE routing and must not redefine the security semantics.
- `src/qwenpaw/cli` owns existing `qwenpaw doctor` and `qwenpaw doctor fix`; health-check orchestration must wrap these as scan-only then confirmed-fix phases.
- `console` owns Settings/Security UI placement and API client calls.
- `thirdparty/clawsec-main/clawsec-main` remains a reused capability source, not a copied implementation mirror.

## Interface Contracts
- Persona baseline protection must expose enablement, protected path listing, drift alert observation, Restore, and Accept operations through backend APIs consumed by console UI.
- Source trust verification must expose a verify-only package API. It may reuse ClawSec guarded skill install or extracted release-verification primitives, but must not install or execute the selected package.
- Health Check must expose scan progress and suggested repairs separately from confirmed fix execution. A scan request is read-only. A fix request requires a second explicit user confirmation and targets one selected repair.
- Health Check full doctor coverage must expose a structured projection with `group`, `id`, `status`, `detail`, `risk`, `recommendation`, `fix_id`, and `deep_only` fields for each check item. The projection must be generated from qwenpaw doctor helper semantics, not by parsing `click.echo` output.
- Default Health Check scan must use `deep=false` and omit channel connectivity and local LLM deep probes. The console/API may offer explicit `deep=true` only as an advanced scan action, and that scan remains read-only.
- Rule integrity must reuse the existing dangerous-shell-rules integrity backend and expose it through the new Integrity Check submenu. Repair remains a separate explicit action.
- Console i18n must route every Integrity Check and Health Check operator-visible string through `console/src/i18n.ts` with English and Simplified Chinese locale coverage in `console/src/locales/en.json` and `console/src/locales/zh.json`; unsupported configured languages may rely on the existing English fallback.
- Health Check progress must expose a localized current-check carousel sourced from the full doctor-derived check list. Completion, failure, cancellation, and interruption must stop carousel rotation without running any doctor fix.

## Testcase Entrypoints
- `tests/integration/security/test_integrity_protection.py::test_integrity_security_menu_default_off`
- `tests/integration/security/test_integrity_protection.py::test_persona_drift_alert_restore_accept`
- `tests/integration/security/test_integrity_protection.py::test_source_trust_verification_package`
- `tests/integration/security/test_integrity_protection.py::test_health_check_scan_and_confirmed_fix`
- `tests/integration/security/test_integrity_protection.py::test_rule_integrity_entry_visible`
- `tests/integration/security/test_integrity_protection.py::test_security_i18n_and_healthcheck_progress_carousel`
- `tests/integration/security/test_integrity_protection.py::test_healthcheck_full_doctor_coverage_projection`

These tests are business-readable acceptance contracts. Coding/Repair may implement behavior behind `tests/integration/security/integrity_harness.py`, but must not rewrite the GIVEN/WHEN/THEN test bodies, testcase names, control points, observation points, or business failure categories without returning to implementation design.

## Persona Baseline Sub-Slice

Persona drift protection (PRD section 一) is specified in detail in `extension/Persona Baseline Guardian Design.md` (v0.6.7), including enable gate, scenario tests with **SOUL.md pilot default**, **P2 Restore/Accept**, and PB-S20 user journey (§18.8).

## Key Implementation Mapping
- Direct: `src/qwenpaw/security` realizes `intent-integrity-protection-delivery`, `intent-persona-baseline-guardian`, `intent-source-trust-verifier`, and `intent-health-check-orchestrator` backend semantics.
- Direct: `console` realizes `intent-integrity-security-console`.
- Indirect: `extension` carries PRD-scoped adapter design and low-intrusion glue under the runtime and console contracts.
- Indirect: `thirdparty/clawsec-main/clawsec-main/skills/soul-guardian` carries persona baseline mechanics.
- Indirect: `thirdparty/clawsec-main/clawsec-main/skills/clawsec-suite/scripts/guarded_skill_install.mjs` carries source trust verification mechanics.
- Indirect: `src/qwenpaw/cli/doctor_cmd.py` and `src/qwenpaw/cli/doctor_fix_runner.py` carry scan and confirmed-fix mechanics.
- Indirect: `src/qwenpaw/security/tool_guard/rules_integrity.py` carries dangerous shell command rule integrity mechanics.
- Direct testcase: `tests/integration/security/test_integrity_protection.py::test_security_i18n_and_healthcheck_progress_carousel` realizes the `ip-e2e-006-security-i18n-progress-carousel` intent acceptance boundary and currently fails until Coding/Repair implements the console i18n and Health Check carousel work.
- Direct testcase: `tests/integration/security/test_integrity_protection.py::test_healthcheck_full_doctor_coverage_projection` realizes the `ip-e2e-007-healthcheck-full-doctor-coverage` intent acceptance boundary and currently fails until Coding/Repair implements the full doctor coverage projection and explicit deep scan path.

## Coding/Repair Constraints
- Do not modify `design/KG/SystemArchitecture.json` in Coding/Repair.
- Do not make feature enablement default-on.
- Do not auto-restore, auto-accept, auto-repair, install, execute, or fix anything before explicit user action.
- Do not put raw HTTP, environment, SQL, GraphQL, or filesystem plumbing into `tests/integration/security/test_integrity_protection.py`.
- Do not treat the PRD plaintext signing private key as production-grade storage. Keep it local/demo unless the user explicitly approves a production key-management design.
- Do not copy ClawSec logic into an unrelated implementation when a stable adapter or extracted verification primitive can reuse it.
- Do not satisfy `ip-e2e-006-security-i18n-progress-carousel` by hiding hardcoded copy behind conditional rendering. Replace hardcoded Integrity Check and Health Check strings with translation keys, add English and Simplified Chinese values, and preserve English fallback through `console/src/i18n.ts`.
- Do not implement Health Check carousel rotation in a way that keeps running after completed, failed, cancelled, or interrupted states. Do not trigger `runIntegrityHealthCheckFix` or any doctor fix from carousel state.
- Do not satisfy `ip-e2e-007-healthcheck-full-doctor-coverage` by parsing CLI stdout from `qwenpaw doctor`. Extract or reuse structured doctor helper semantics and keep scan and fix phases separate.
- Do not enable `--deep` connectivity by default. Deep-only items must be absent from the default scan and present only through an explicit deep scan control.

## Expected First Failure Signals
- `Integrity_Default_Off_Gap`
- `Persona_Drift_Protection_Gap`
- `Source_Trust_Verification_Gap`
- `Health_Check_Confirmed_Fix_Gap`
- `Rule_Integrity_Console_Entry_Gap`
- `Security_I18n_Progress_Carousel_Gap`
- `Health_Check_Full_Doctor_Coverage_Gap`

These failures are expected until Coding/Repair implements the runtime and console behavior.
