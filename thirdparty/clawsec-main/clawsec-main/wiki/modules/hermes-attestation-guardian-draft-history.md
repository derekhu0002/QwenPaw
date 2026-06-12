# Module History: Hermes Attestation Guardian Draft (Archived)

## Purpose
This page preserves the original planning draft that led to `hermes-attestation-guardian` v0.0.1.
It is historical context, not current behavior contract.

## Status
- Draft date: 2026-04-15
- Current status: implemented in repository as `skills/hermes-attestation-guardian` v0.0.1
- Source of truth for live behavior: skill code, tests, and `wiki/modules/hermes-attestation-guardian.md`

## What the draft got right
- Hermes-only positioning (not OpenClaw hook runtime scope).
- Fail-closed verification as a core requirement.
- Deterministic attestation and digest binding requirements.
- Baseline-vs-current drift detection with severity ranking.
- Safe cron automation expectations (explicit apply, non-destructive defaults).

## Original design intent (summarized)
1) Identity and scope
- Name should clearly indicate Hermes scope and guardian role.
- Metadata should make platform targeting explicit.

2) Security outcomes
- Snapshot posture and integrity-sensitive inputs.
- Detect risky toggles, verification regressions, and trust/file drift.
- Prioritize high-signal alerts for operators.

3) Alignment rules
- Keep side effects under Hermes paths.
- Avoid destructive remediation in MVP.
- Keep operator-facing criticality clear.

4) Packaging/release compatibility
- Match ClawSec skill metadata and changelog requirements.
- Ensure local validation and test gates pass before release.

5) Delegate implementation scope
- Build generator, verifier, diff logic, cron helper, and tests.
- Keep docs aligned to implemented behavior.

## What changed from draft to implementation
- Implementation hardened path-scope checks (including symlink-aware escape defense).
- Verifier baseline trust was made explicit and fail-closed before diffing.
- Cron managed-marker parser hardened to fail closed on malformed marker structure.
- Wiki documentation now maps each PR claim to wiring and tests with human-readable operator guidance.

## Where to look now
- Live module documentation:
  - `wiki/modules/hermes-attestation-guardian.md`
- Live skill implementation:
  - `skills/hermes-attestation-guardian/`
- Validation tests:
  - `skills/hermes-attestation-guardian/test/`
