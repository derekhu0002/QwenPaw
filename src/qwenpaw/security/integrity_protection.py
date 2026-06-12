# -*- coding: utf-8 -*-
"""Opt-in Integrity Protection services.

The module keeps the delivery slice passive by default. Callers must explicitly
enable or invoke each action before any baseline, health, or rule operation can
mutate state.
"""
from __future__ import annotations

import contextlib
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .tool_guard.rules_integrity import verify_default_builtin_rule_files


@dataclass(frozen=True)
class IntegrityProtectionSettings:
    persona_protection_enabled: bool = False
    health_check_enabled: bool = False
    rule_integrity_check_passive: bool = True
    protected_paths: tuple[str, ...] = ()
    menus: tuple[str, ...] = (
        "Tool Guard",
        "File Guard",
        "Integrity Check",
        "Health Check",
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PersonaDriftAlert:
    path: str
    previous_sha256: str
    current_sha256: str
    detected_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PersonaBaselineState:
    enabled: bool
    protected_paths: tuple[str, ...]
    alerts: tuple[PersonaDriftAlert, ...] = ()
    startup_scan_ran: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["alerts"] = [alert.to_dict() for alert in self.alerts]
        return data


@dataclass(frozen=True)
class HealthCheckScanResult:
    scan_id: str
    read_only: bool
    progress: int
    check_items: tuple[dict[str, Any], ...]
    risk_summary: tuple[str, ...]
    repair_suggestions: tuple[dict[str, Any], ...]
    mutated_files: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HealthCheckFixResult:
    confirmed: bool
    selected_repair: str
    fix_id: str
    executed: bool
    exit_code: int
    output: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_default_integrity_settings() -> IntegrityProtectionSettings:
    """Return Integrity Protection settings including persisted persona state."""

    from .persona_baseline_bridge import get_integrity_settings_projection

    return get_integrity_settings_projection()


def _load_persona_baseline_guardian():
    from .persona_baseline_bridge import PersonaBaselineGuardian as BridgeGuardian

    return BridgeGuardian


class PersonaBaselineGuardian:
    """Delegate persona baseline operations to extension implementation."""

    def __init__(self, workspace_root: Path, state_dir: Path | None = None) -> None:
        self._delegate = _load_persona_baseline_guardian()(
            workspace_root,
            state_dir=state_dir,
        )

    def enable(self, protected_paths: tuple[str, ...]) -> PersonaBaselineState:
        return self._delegate.enable(protected_paths)

    def scan(self) -> PersonaBaselineState:
        return self._delegate.scan()

    def restore(self, relative_path: str) -> bool:
        return self._delegate.restore(relative_path)

    def accept(self, relative_path: str) -> bool:
        return self._delegate.accept(relative_path)


_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXTENSION_DIR = _REPO_ROOT / "extension"
if str(_EXTENSION_DIR) not in sys.path:
    sys.path.insert(0, str(_EXTENSION_DIR))

from health_check.fix import run_confirmed_health_fix  # noqa: E402
from health_check.scanner import run_health_check_scan  # noqa: E402


def run_rule_integrity_check() -> dict[str, Any]:
    """Run the existing dangerous-shell-rule integrity backend passively."""

    return verify_default_builtin_rule_files().to_dict()


@dataclass
class IntegrityProtectionProbeResult:
    settings: IntegrityProtectionSettings = field(default_factory=get_default_integrity_settings)
    persona_state: PersonaBaselineState | None = None
    health_scan: HealthCheckScanResult | None = None
    health_fix: HealthCheckFixResult | None = None
    rule_integrity: dict[str, Any] | None = None


@contextlib.contextmanager
def capture_file_writes(workspace_root: Path):
    """Capture file mtimes before and after a read-only operation."""

    before = {
        p: p.stat().st_mtime_ns
        for p in workspace_root.rglob("*")
        if p.is_file()
    }
    yield lambda: tuple(
        str(p.relative_to(workspace_root))
        for p in workspace_root.rglob("*")
        if p.is_file() and before.get(p) != p.stat().st_mtime_ns
    )
