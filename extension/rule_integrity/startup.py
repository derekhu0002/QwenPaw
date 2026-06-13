# -*- coding: utf-8 -*-
"""Application lifecycle hooks for rule integrity."""
from __future__ import annotations

import asyncio
import logging

from .verifier import verify_default_builtin_rule_files

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 5.0


async def periodic_rule_integrity_check(
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> None:
    """Background task: re-verify bundled rules on a fixed interval."""

    while True:
        try:
            await asyncio.to_thread(verify_default_builtin_rule_files)
        except Exception:  # pylint: disable=broad-except
            logger.warning(
                "Periodic built-in rule integrity check failed",
                exc_info=True,
            )
        await asyncio.sleep(poll_interval_seconds)
