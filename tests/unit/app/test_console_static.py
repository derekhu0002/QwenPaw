# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from qwenpaw.app.console_static import resolve_console_static_dir


def _touch_index(path: Path) -> None:
    path.mkdir(parents=True)
    (path / "index.html").write_text("<!doctype html>", encoding="utf-8")


def test_explicit_console_static_dir_wins(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    pkg_dir = tmp_path / "site-packages" / "qwenpaw"
    explicit = tmp_path / "custom-console"
    _touch_index(cwd / "console" / "dist")
    _touch_index(pkg_dir / "console")

    assert (
        resolve_console_static_dir(
            str(explicit),
            cwd=cwd,
            pkg_dir=pkg_dir,
        )
        == str(explicit)
    )


def test_source_checkout_console_dist_wins_over_packaged_assets(
    tmp_path: Path,
) -> None:
    cwd = tmp_path / "repo"
    pkg_dir = tmp_path / "site-packages" / "qwenpaw"
    source_dist = cwd / "console" / "dist"
    packaged_dist = pkg_dir / "console"
    _touch_index(source_dist)
    _touch_index(packaged_dist)

    assert (
        resolve_console_static_dir("", cwd=cwd, pkg_dir=pkg_dir)
        == str(source_dist)
    )


def test_editable_install_repo_dist_wins_over_packaged_assets(
    tmp_path: Path,
) -> None:
    pkg_dir = tmp_path / "repo" / "src" / "qwenpaw"
    repo_dist = tmp_path / "repo" / "console" / "dist"
    packaged_dist = pkg_dir / "console"
    _touch_index(repo_dist)
    _touch_index(packaged_dist)

    assert (
        resolve_console_static_dir(
            "",
            cwd=tmp_path / "elsewhere",
            pkg_dir=pkg_dir,
        )
        == str(repo_dist)
    )
