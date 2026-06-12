# -*- coding: utf-8 -*-
"""Opt-in Integrity Protection services.

The module keeps the delivery slice passive by default. Callers must explicitly
enable or invoke each action before any baseline, package, health, or rule
operation can mutate state.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ..constant import WORKING_DIR
from .tool_guard.rules_integrity import verify_default_builtin_rule_files


DEMO_SIGNATURE_SCHEME = "qwenpaw-integrity-demo-ed25519-v1"
_DEMO_PRIVATE_SEED_HEX = (
    "6f7c2f1a8c9b4d3e55aa108709e8db4fa67c8427b2d6e4f998014e6a459b8f21"
)
_STATE_ROOT_NAME = "integrity-protection"

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _demo_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(_DEMO_PRIVATE_SEED_HEX))


def demo_public_key_hex() -> str:
    return (
        _demo_private_key()
        .public_key()
        .public_bytes(Encoding.Raw, PublicFormat.Raw)
        .hex()
    )


def _canonical_package_manifest(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _state_root(base_dir: Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else WORKING_DIR
    return root / _STATE_ROOT_NAME


@dataclass(frozen=True)
class IntegrityProtectionSettings:
    persona_protection_enabled: bool = False
    source_trust_verification_enabled: bool = False
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
class SourceTrustResult:
    status: str
    trusted: bool
    reason: str
    publisher: str | None = None
    package_sha256: str | None = None
    installed: bool = False
    executed: bool = False
    verification_scheme: str = DEMO_SIGNATURE_SCHEME

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def create_demo_signed_package(
    package_path: Path,
    *,
    publisher: str = "qwenpaw-local-demo",
    content: bytes = b"trusted skill package content\n",
) -> Path:
    """Create a signed local/demo release package for verification flows."""

    package_path.parent.mkdir(parents=True, exist_ok=True)
    package_sha = _sha256_bytes(content)
    manifest = {
        "signature_scheme": DEMO_SIGNATURE_SCHEME,
        "publisher": publisher,
        "package_sha256": package_sha,
        "public_key": demo_public_key_hex(),
    }
    signature = _demo_private_key().sign(_canonical_package_manifest(manifest)).hex()
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("payload.bin", content)
        zf.writestr("qwenpaw_integrity_manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("qwenpaw_integrity_manifest.sig", signature)
    return package_path


def verify_source_trust_package(package_path: Path) -> SourceTrustResult:
    """Verify a package signature without installing or executing it."""

    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            required = {
                "payload.bin",
                "qwenpaw_integrity_manifest.json",
                "qwenpaw_integrity_manifest.sig",
            }
            missing = sorted(required - names)
            if missing:
                return SourceTrustResult(
                    status="verification_error",
                    trusted=False,
                    reason=f"missing package trust files: {', '.join(missing)}",
                )
            payload = zf.read("payload.bin")
            manifest = json.loads(
                zf.read("qwenpaw_integrity_manifest.json").decode("utf-8"),
            )
            signature = bytes.fromhex(
                zf.read("qwenpaw_integrity_manifest.sig").decode("ascii").strip(),
            )
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError, ValueError) as exc:
        return SourceTrustResult(
            status="verification_error",
            trusted=False,
            reason=str(exc),
        )

    package_sha = _sha256_bytes(payload)
    if manifest.get("signature_scheme") != DEMO_SIGNATURE_SCHEME:
        return SourceTrustResult(
            status="untrusted",
            trusted=False,
            reason="unsupported signature scheme",
            package_sha256=package_sha,
        )
    if manifest.get("package_sha256") != package_sha:
        return SourceTrustResult(
            status="untrusted",
            trusted=False,
            reason="package payload sha256 mismatch",
            publisher=str(manifest.get("publisher") or ""),
            package_sha256=package_sha,
        )
    if manifest.get("public_key") != demo_public_key_hex():
        return SourceTrustResult(
            status="untrusted",
            trusted=False,
            reason="publisher public key is not trusted by local demo boundary",
            publisher=str(manifest.get("publisher") or ""),
            package_sha256=package_sha,
        )

    try:
        Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(demo_public_key_hex()),
        ).verify(signature, _canonical_package_manifest(manifest))
    except (InvalidSignature, ValueError) as exc:
        return SourceTrustResult(
            status="untrusted",
            trusted=False,
            reason=f"signature verification failed: {exc}",
            publisher=str(manifest.get("publisher") or ""),
            package_sha256=package_sha,
        )

    return SourceTrustResult(
        status="trusted",
        trusted=True,
        reason="signature verified with local/demo trusted publisher key",
        publisher=str(manifest.get("publisher") or ""),
        package_sha256=package_sha,
    )



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
    source_trust_results: tuple[SourceTrustResult, ...] = ()
    health_scan: HealthCheckScanResult | None = None
    health_fix: HealthCheckFixResult | None = None
    rule_integrity: dict[str, Any] | None = None
    installed_packages: int = 0
    executed_packages: int = 0


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
