# -*- coding: utf-8 -*-
"""Health Check extension — doctor projection for Settings/Security."""

from .constants import DEFAULT_HEALTH_FIX_ID
from .fix import run_confirmed_health_fix
from .scanner import run_health_check_scan

__all__ = [
    "DEFAULT_HEALTH_FIX_ID",
    "run_confirmed_health_fix",
    "run_health_check_scan",
]
