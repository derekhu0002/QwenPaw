# -*- coding: utf-8 -*-
"""Integrity checks for built-in tool guard rule files.

This module deliberately stays independent from the rule matching logic. The
guardian calls it before loading bundled rules, and callers can read the latest
status through a lightweight in-process cache.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
)

logger = logging.getLogger(__name__)

MANIFEST_NAME = "rules_manifest.json"
SIGNATURE_NAME = "rules_manifest.sig"
SIGNATURE_SCHEME = "ed25519-v1"
HASH_SCHEME = "sha256"

# Public key for the official built-in tool-rule manifest signature.
# The matching private key is used only by release tooling and is not shipped.
_PUBLIC_KEY_HEX = (
    "de908efdc39b232c0d1be7721f6e76ced600a69e0ffe4a20635a3608e3e3f157"
)


@dataclass(frozen=True)
class RuleIntegrityFinding:
    """One rule integrity verification finding."""

    file: str
    reason: str
    expected_sha256: str | None = None
    actual_sha256: str | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuleIntegrityResult:
    """Latest built-in rule integrity verification result."""

    ok: bool
    status: str
    message: str
    checked_at: str | None
    findings: list[RuleIntegrityFinding]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["findings"] = [f.to_dict() for f in self.findings]
        return data


_UNKNOWN_RESULT = RuleIntegrityResult(
    ok=True,
    status="unknown",
    message="Tool guard rule integrity has not been checked yet.",
    checked_at=None,
    findings=[],
)
_last_status: RuleIntegrityResult | None = None
_last_logged_failure: tuple[Any, ...] | None = None


def _default_rules_dir() -> Path:
    return Path(__file__).resolve().parent / "rules"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _result(
    *,
    ok: bool,
    status: str,
    findings: list[RuleIntegrityFinding] | None = None,
) -> RuleIntegrityResult:
    return RuleIntegrityResult(
        ok=ok,
        status=status,
        message=(
            "Built-in tool guard rules are intact."
            if ok
            else "内置检测规则已被篡改"
        ),
        checked_at=_utc_now(),
        findings=findings or [],
    )


def get_last_rule_integrity_status() -> RuleIntegrityResult:
    """Return the latest verification status without touching the filesystem."""

    return _last_status or _UNKNOWN_RESULT


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(rules_dir: Path) -> tuple[dict[str, Any], bytes] | None:
    manifest_path = rules_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        return None
    raw = manifest_path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest root is not an object")
    return data, raw


def _verify_signature(rules_dir: Path, manifest_bytes: bytes) -> bool:
    signature_path = rules_dir / SIGNATURE_NAME
    if not signature_path.is_file():
        raise FileNotFoundError(SIGNATURE_NAME)
    signature_hex = signature_path.read_text(encoding="ascii").strip()
    signature = bytes.fromhex(signature_hex)
    public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(_PUBLIC_KEY_HEX))
    public_key.verify(signature, manifest_bytes)
    return True


def _log_failure(result: RuleIntegrityResult) -> None:
    global _last_logged_failure

    fingerprint = (
        result.status,
        tuple(
            (
                finding.file,
                finding.reason,
                finding.expected_sha256,
                finding.actual_sha256,
                finding.detail,
            )
            for finding in result.findings
        ),
    )
    if fingerprint == _last_logged_failure:
        return
    _last_logged_failure = fingerprint
    logger.error(
        "Built-in tool guard rule integrity check failed: status=%s "
        "message=%s findings=%s action=warn_only_loaded_anyway",
        result.status,
        result.message,
        [f.to_dict() for f in result.findings],
    )


def verify_builtin_rule_files(
    rules_dir: Path,
    rule_files: list[str],
) -> RuleIntegrityResult:
    """Verify bundled tool-rule files and cache the latest result.

    The first implementation is warn-only: failures are reported through logs
    and the status API, but rule loading continues.
    """

    global _last_status

    try:
        loaded = _load_manifest(rules_dir)
        if loaded is None:
            result = _result(
                ok=False,
                status="missing_manifest",
                findings=[
                    RuleIntegrityFinding(
                        file=MANIFEST_NAME,
                        reason="missing_manifest",
                    ),
                ],
            )
            _last_status = result
            _log_failure(result)
            return result

        manifest, manifest_bytes = loaded
        if manifest.get("signature_scheme") != SIGNATURE_SCHEME:
            raise ValueError(
                f"unsupported signature scheme: "
                f"{manifest.get('signature_scheme')!r}",
            )
        if manifest.get("hash_scheme") != HASH_SCHEME:
            raise ValueError(
                f"unsupported hash scheme: {manifest.get('hash_scheme')!r}",
            )

        try:
            _verify_signature(rules_dir, manifest_bytes)
        except FileNotFoundError:
            result = _result(
                ok=False,
                status="missing_signature",
                findings=[
                    RuleIntegrityFinding(
                        file=SIGNATURE_NAME,
                        reason="missing_signature",
                    ),
                ],
            )
            _last_status = result
            _log_failure(result)
            return result
        except (InvalidSignature, ValueError) as exc:
            result = _result(
                ok=False,
                status="manifest_invalid",
                findings=[
                    RuleIntegrityFinding(
                        file=MANIFEST_NAME,
                        reason="signature_invalid",
                        detail=str(exc),
                    ),
                ],
            )
            _last_status = result
            _log_failure(result)
            return result

        files = manifest.get("files", {})
        if not isinstance(files, dict):
            raise ValueError("manifest 'files' is not an object")

        findings: list[RuleIntegrityFinding] = []
        for filename in rule_files:
            entry = files.get(filename)
            if not isinstance(entry, dict):
                findings.append(
                    RuleIntegrityFinding(
                        file=filename,
                        reason="missing_manifest_entry",
                    ),
                )
                continue

            expected = entry.get("sha256")
            if not isinstance(expected, str) or not expected:
                findings.append(
                    RuleIntegrityFinding(
                        file=filename,
                        reason="missing_expected_sha256",
                    ),
                )
                continue

            path = rules_dir / filename
            if not path.is_file():
                findings.append(
                    RuleIntegrityFinding(
                        file=filename,
                        reason="missing_rule_file",
                        expected_sha256=expected,
                    ),
                )
                continue

            actual = _sha256_file(path)
            if actual != expected:
                findings.append(
                    RuleIntegrityFinding(
                        file=filename,
                        reason="sha256_mismatch",
                        expected_sha256=expected,
                        actual_sha256=actual,
                    ),
                )

        result = (
            _result(ok=True, status="ok")
            if not findings
            else _result(ok=False, status="tampered", findings=findings)
        )
        _last_status = result
        if result.ok:
            global _last_logged_failure

            _last_logged_failure = None
        if not result.ok:
            _log_failure(result)
        return result
    except Exception as exc:  # pylint: disable=broad-except
        result = _result(
            ok=False,
            status="check_failed",
            findings=[
                RuleIntegrityFinding(
                    file=MANIFEST_NAME,
                    reason="check_failed",
                    detail=str(exc),
                ),
            ],
        )
        _last_status = result
        _log_failure(result)
        return result


def verify_default_builtin_rule_files() -> RuleIntegrityResult:
    """Verify the default built-in tool guard rule files."""

    return verify_builtin_rule_files(
        _default_rules_dir(),
        ["dangerous_shell_commands.yaml"],
    )
