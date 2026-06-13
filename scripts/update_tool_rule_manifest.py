# -*- coding: utf-8 -*-
"""Backward-compatible entrypoint for rule manifest signing."""
from __future__ import annotations

import runpy
from pathlib import Path

_TARGET = (
    Path(__file__).resolve().parent.parent
    / "extension"
    / "rule_integrity"
    / "scripts"
    / "update_tool_rule_manifest.py"
)

if __name__ == "__main__":
    runpy.run_path(str(_TARGET), run_name="__main__")
