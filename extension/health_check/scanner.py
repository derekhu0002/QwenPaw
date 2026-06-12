# -*- coding: utf-8 -*-
"""Read-only Health Check scan orchestration."""
from __future__ import annotations

import hashlib
from pathlib import Path

from qwenpaw.constant import WORKING_DIR
from qwenpaw.security.integrity_protection import HealthCheckScanResult

from .constants import DEFAULT_HEALTH_FIX_ID
from .projection import _collect_doctor_projection_items


def run_health_check_scan(
    base_dir: Path | None = None,
    *,
    deep: bool = False,
    timeout: float = 1.0,
    llm_timeout: float = 1.0,
) -> HealthCheckScanResult:
    """Return read-only structured qwenpaw doctor health-check projection."""

    root = Path(base_dir) if base_dir is not None else WORKING_DIR
    check_items = _collect_doctor_projection_items(
        root,
        deep=deep,
        timeout=timeout,
        llm_timeout=llm_timeout,
    )
    risks = tuple(
        item["id"]
        for item in check_items
        if item["status"] in {"risk", "suggestion"} and not item["deep_only"]
    )
    repair_suggestions = [
        {
            "label": "repair_missing_console_static_build",
            "doctor_fix_id": DEFAULT_HEALTH_FIX_ID,
            "requires_confirmation": True,
        },
    ]
    seen_fix_ids = {DEFAULT_HEALTH_FIX_ID}
    for item in check_items:
        fix_id = item.get("fix_id")
        if not isinstance(fix_id, str) or not fix_id or fix_id in seen_fix_ids:
            continue
        seen_fix_ids.add(fix_id)
        repair_suggestions.append(
            {
                "label": f"repair_{item['id']}",
                "doctor_fix_id": fix_id,
                "requires_confirmation": True,
            },
        )
    return HealthCheckScanResult(
        scan_id=(
            "health-scan-"
            f"{hashlib.sha256((str(root) + ':' + str(deep)).encode()).hexdigest()[:12]}"
        ),
        read_only=True,
        progress=100,
        check_items=check_items,
        risk_summary=risks,
        repair_suggestions=tuple(repair_suggestions),
    )
