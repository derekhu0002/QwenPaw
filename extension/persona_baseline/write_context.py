# -*- coding: utf-8 -*-
"""Optional provenance override for nested persona maintenance operations."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

_persona_maintenance: ContextVar[bool] = ContextVar(
    "persona_maintenance",
    default=False,
)


def is_persona_maintenance() -> bool:
    return _persona_maintenance.get()


@contextmanager
def persona_maintenance_context():
    token = _persona_maintenance.set(True)
    try:
        yield
    finally:
        _persona_maintenance.reset(token)
