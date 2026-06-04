# QwenPaw Security Center Introduction

QwenPaw now includes a deploy-owned Security Center slice that stays physically separate from the edge runtime. The edge node remains responsible for local audit evidence and tool-boundary enforcement, while Security Center receives HTTP uplinks only, maintains cloud-side shadow state, and surfaces operator-facing anomaly and rejection evidence without reading the edge working directory directly.

## External Interfaces

- Backend API: `deploy/api/app.py`
  - Recovery handshake: `POST /security-center/v1/recovery/handshake`
  - Rejected-event uplink: `POST /security-center/v1/uplinks/rejections`
  - Lockdown uplink: `POST /security-center/v1/uplinks/lockdowns`
  - Operator overview: `GET /security-center/v1/operator/overview`
  - Voucher lookup: `GET /security-center/v1/operator/vouchers/{nonce}`
  - Divergence timeline: `GET /security-center/v1/operator/timelines/{client_id}`
  - Realtime alerts: `GET /security-center/v1/operator/stream`

- Operator web: `deploy/web/index.html`
  - Renders anomaly dashboard, trust-state and recovery view, rejected-event evidence, hash-break curve chart, and Security_Rejection_Nonce Voucher display.
  - Subscribes to deploy/api over Server-Sent Events instead of manual refresh.

## Launch

- Backend API: `python -m deploy.api.app`
- Operator web: `python -m deploy.web.server`
- Showcase helper: `python -m deploy.api.showcase show-plan`
