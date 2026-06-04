from __future__ import annotations

from pathlib import Path


def test_operator_web_assets_keep_realtime_dashboard_roles() -> None:
    """Control point: read the operator web static assets from disk.

    Observation point: the web frontend must keep a realtime alert stream,
    voucher display, trust-state view, and hash-break chart roles.
    """

    repo_root = Path(__file__).resolve().parents[3]
    html = (repo_root / "deploy" / "web" / "index.html").read_text(encoding="utf-8")
    js = (repo_root / "deploy" / "web" / "app.js").read_text(encoding="utf-8")

    for marker in (
        "Hash-break curve chart",
        "Nonce Voucher display",
        "Trust-state and recovery view",
        "Realtime operator alert",
    ):
        assert marker in html

    for marker in (
        "new EventSource",
        "/security-center/v1/operator/stream",
        "/security-center/v1/operator/overview",
        "/security-center/v1/operator/timelines/",
    ):
        assert marker in js
