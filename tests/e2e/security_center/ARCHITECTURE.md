---
contract_type: implementation-architecture-element
contract_version: 1
scope: stable-element
element_name: security-center-web-e2e-entrypoints
element_kind: SecurityCenterWebE2EEntrypointZone
element_path: tests/e2e/security_center
---

## Implementation Architecture Contract

### Responsibility
- Own the explicit operator Web consumption entrypoint for Security Event Ingestion V1.
- Keep Web acceptance assertions business-readable by routing page/API plumbing through `tests/integration/security/security_event_harness.py`.
- Preserve the stable detail URL, list ordering, source/type/severity/time filter correctness, configured-field display, event type display name, undefined-field display, and bounded raw payload observation points required by `sec-event-ingestion-v1-render-web-list-and-detail`.

### Out Of Scope
- Owning production backend routes under `deploy/api`.
- Owning production Web rendering under `deploy/web`.
- Replacing the explicit Web inbox baseline with a unit-only component test.

### Explicit Testcase Entrypoints
- testcase_name: sec-event-ingestion-v1-render-web-list-and-detail
  entry_path: test_security_event_inbox.py::test_web_lists_filters_and_opens_event_detail
  control_point: seed multiple accepted security events through the protected harness, open the operator Web inbox route, apply source/type/severity/time filters, and navigate to a stable detail URL by sourceSystem plus eventId
  observation_point: the inbox defaults to receivedAt descending, source/type/severity/time filters return only matching rows, event type display name and configured list payload fields are visible, the same detail URL reopens, and detail displays base facts, labeled structured payload, undefined fields, and bounded read-only raw payload

### Protected Fixtures
- `tests/integration/security/security_event_harness.py`
- `tests/e2e/security_center/conftest.py`

### Notes
- This entrypoint is expected to fail until `deploy/api` and `deploy/web` implement the Security Event Ingestion V1 APIs and inbox routes.
- Coding/Repair may improve production pages and APIs, but must not move or weaken this explicit entrypoint without a new implementation-architecture change.
- `conftest.py` must continue to load `tests.integration.conftest` so the Web entrypoint uses the same real Security Center API/Web/runtime subprocess baseline as the integration security entrypoints.
