# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


def _has_console_index(path: Path) -> bool:
    return path.is_dir() and (path / "index.html").exists()


def resolve_console_static_dir(
    static_dir: str,
    *,
    cwd: Path,
    pkg_dir: Path,
) -> str:
    """Resolve the console static assets directory.

    Source checkouts should prefer their freshly built frontend assets over
    packaged assets from an installed qwenpaw distribution.
    """
    if static_dir:
        return static_dir

    for subdir in ("console/dist", "console_dist"):
        candidate = cwd / subdir
        if _has_console_index(candidate):
            return str(candidate)

    repo_dir = pkg_dir.parent.parent
    candidate = repo_dir / "console" / "dist"
    if _has_console_index(candidate):
        return str(candidate)

    candidate = pkg_dir / "console"
    if _has_console_index(candidate):
        return str(candidate)

    return str(cwd / "console" / "dist")
