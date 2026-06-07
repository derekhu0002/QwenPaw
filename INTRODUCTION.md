# QwenPaw Security Center Introduction

QwenPaw now includes a deploy-owned Security Center slice that stays physically separate from the edge runtime. The edge node remains responsible for local audit evidence and tool-boundary enforcement, while Security Center receives HTTP uplinks only, maintains cloud-side shadow state, and surfaces operator-facing anomaly and rejection evidence without reading the edge working directory directly.

## External Interfaces

- Backend API: `deploy/api/app.py`
  - Recovery handshake: `POST /security-center/v1/recovery/handshake`
    - Accepts edge-reported head hash plus anchor and sequence metadata, and keeps recovery gated until any missing gap is explicitly validated.
    - Distinguishes `ALIGNED`, `DIVERGED`, and `GAP_VALIDATION_REQUIRED` instead of treating head-hash equality as automatic recovery.
  - Trusted-anchor uplink: `POST /security-center/v1/uplinks/trusted-anchors`
    - Accepts normal critical anchor evidence such as `USER_CONFIRMATION`, recomputes the anchor materials server-side, and advances the cloud trusted anchor only when the uploaded evidence is independently reproducible.
  - Rejected-event uplink: `POST /security-center/v1/uplinks/rejections`
  - Lockdown uplink: `POST /security-center/v1/uplinks/lockdowns`
  - Operator overview: `GET /security-center/v1/operator/overview`
    - Projects canonical Security Center client state while also exposing session-scoped alias entries so operator and acceptance clients can continue to look up the live runtime by the authenticated session id.
  - Voucher lookup: `GET /security-center/v1/operator/vouchers/{nonce}`
  - Divergence timeline: `GET /security-center/v1/operator/timelines/{client_id}`
    - Accepts either the canonical Security Center client id or a session alias and returns last trusted anchor, current edge-reported head, gap status, fork point, recovery gate state, and `canonical_client_id` for operator review.
  - Realtime alerts: `GET /security-center/v1/operator/stream`

- Operator web: `deploy/web/index.html`
  - Renders anomaly dashboard, trust-state and recovery view, rejected-event evidence, hash-break curve chart, gap-validation state, recovery gate state, and Security_Rejection_Nonce Voucher display.
  - Subscribes to deploy/api over Server-Sent Events instead of manual refresh.

## Launch

- Backend API: `python -m deploy.api.app`
- Operator web: `python -m deploy.web.server`
- Showcase helper: `python -m deploy.api.showcase show-plan`
