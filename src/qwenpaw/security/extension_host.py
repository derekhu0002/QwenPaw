# -*- coding: utf-8 -*-
"""Single host entry for optional security extension hooks."""
from __future__ import annotations

from .persona_baseline_bridge import (
    get_integrity_settings_projection,
    get_persona_service,
    notify_file_saved,
    run_startup_scan_if_enabled,
    stream_persona_events,
)

__all__ = [
    "get_integrity_settings_projection",
    "get_persona_service",
    "notify_file_saved",
    "run_startup_scan_if_enabled",
    "stream_persona_events",
]
