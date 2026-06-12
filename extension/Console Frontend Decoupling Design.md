# Console Frontend Extension Decoupling Design

## Purpose

Refactor Integrity Protection–related Console code into `console/src/extension/` without changing runtime behavior. This document mirrors the backend `extension/` layout (persona baseline + health check) and defers **source trust** and **rule integrity** UI decoupling.

## Principles

1. **Behavior freeze:** Move/re-export only; no changes to API payloads, state transitions, UI copy, or effect ordering.
2. **Backward-compatible imports:** Legacy paths (`utils/persona*`, `hooks/usePersonaDriftWatch`, etc.) re-export from `@extension/*` until callers migrate.
3. **Dependency direction:** `extension/*` may import `@/api`, `@/pages/Settings/Security/index.module.less` (shared Security styles). Host pages import `@extension/*/index`, not deep `lib/` paths.
4. **Out of scope (this phase):** Source trust (C), rule integrity backend split (D), backend `src/qwenpaw` decoupling.

## Directory Layout

```
console/src/extension/
├── ARCHITECTURE.md
├── shared/
│   └── inbox/
│       └── inboxEvents.ts          # Generic Inbox changed CustomEvent
├── persona_baseline/
│   ├── index.ts
│   ├── api/client.ts
│   ├── components/
│   │   ├── PersonaDriftAlertNotifier/
│   │   └── PersonaProtectionSection.tsx   # Context + embedded Integrity Check persona UI
│   ├── hooks/usePersonaDriftWatch.ts
│   └── lib/
│       ├── alertActions.ts
│       ├── driftDisplay.ts
│       ├── driftAlertItems.ts
│       └── navigation.ts
└── health_check/
    ├── index.ts
    ├── api/client.ts
    ├── components/HealthCheckSection.tsx
    └── lib/scanUi.ts
```

Path alias: `@extension/*` → `console/src/extension/*` (Vite + `tsconfig.app.json`).

## Module Responsibilities

| Module | Owns |
|--------|------|
| `persona_baseline` | Persona API client, SSE watch, drift alert notifier, Restore/Accept actions, Inbox deep links, Integrity Check persona panel |
| `health_check` | Health scan/fix API client, Health Check tab UI |
| `shared/inbox` | `INBOX_CHANGED_EVENT` bus (used by persona + Sidebar + Inbox) |

## Host Integration (thin shell)

| Host file | Role after decoupling |
|-----------|---------------------|
| `layouts/MainLayout` | Renders `PersonaDriftAlertNotifier` from `@extension/persona_baseline` |
| `pages/Settings/Security/index.tsx` | Tabs; imports `HealthCheckSection` from extension |
| `pages/Settings/Security/components/IntegrityCheckSection.tsx` | Source trust + rule integrity + composes persona panel from extension |
| `api/modules/security.ts` | Tool Guard / File Guard / etc. unchanged; persona + health methods delegate to extension clients |
| `locales/en.json`, `zh.json` | Unchanged; keys remain `security.integrityProtection.*`, `security.healthCheck.*` |

## Persona Panel Split

`IntegrityCheckSection` keeps:

- Aggregate `IntegrityProtectionSettings` load (`Promise.all` with persona `loadPersonaData` preserved)
- Source trust verify UI
- Rule integrity table

Persona UI moves to `PersonaProtectionSection` (Provider + compound parts) with the same DOM structure inside the first Card and alert cards.

## Testing

- Co-locate tests under each extension module (or keep legacy test paths re-exporting targets).
- Update `scripts/persona-protection-selftest.manifest.json` and `scripts/health-check-selftest.manifest.json` frontend targets.
- Verify: `run-persona-protection-selftest.py`, `run-health-check-selftest.py`, `npm run build`.

## Future Phases

- Backend: `extension/health_check/`, shrink `integrity_protection.py`
- Console: `extension/source_trust/` when C is scheduled
- Architecture guard: forbid new `persona*` files outside `console/src/extension/`

## Related Documents

- `extension/ARCHITECTURE.md` — backend extension zone
- `extension/Persona Baseline Guardian Design.md`
- `console/ARCHITECTURE.md` — Settings/Security console contract
