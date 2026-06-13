# -*- coding: utf-8 -*-
"""Path resolution for bundled tool guard rule assets."""
from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def repo_root() -> Path:
    return _REPO_ROOT


def default_rules_dir() -> Path:
    """Return the shipped built-in rules directory under tool_guard."""

    return (
        _REPO_ROOT
        / "src"
        / "qwenpaw"
        / "security"
        / "tool_guard"
        / "rules"
    )
