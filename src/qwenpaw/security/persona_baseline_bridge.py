# -*- coding: utf-8 -*-
"""Thin bridge from qwenpaw core into extension/persona_baseline."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXTENSION_DIR = _REPO_ROOT / "extension"
if str(_EXTENSION_DIR) not in sys.path:
    sys.path.insert(0, str(_EXTENSION_DIR))

from persona_baseline.host_bridge import (  # noqa: E402
    CONFIRM_ACCEPT_PHRASE,
    CONFIRM_REESTABLISH_PHRASE,
    CONFIRM_RESTORE_PHRASE,
    PersonaBaselineGuardian,
    get_integrity_settings_projection,
    get_persona_service,
    notify_file_saved,
    run_startup_scan_if_enabled,
    stream_persona_events,
)

__all__ = [
    "CONFIRM_ACCEPT_PHRASE",
    "CONFIRM_REESTABLISH_PHRASE",
    "CONFIRM_RESTORE_PHRASE",
    "PersonaBaselineGuardian",
    "get_integrity_settings_projection",
    "get_persona_service",
    "notify_file_saved",
    "run_startup_scan_if_enabled",
    "stream_persona_events",
]
