# -*- coding: utf-8 -*-
"""Integrity checks for built-in tool guard rule files.

This module deliberately stays independent from the rule matching logic. The
guardian calls it before loading bundled rules, and callers can read the latest
status through a lightweight in-process cache.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
)

logger = logging.getLogger(__name__)

MANIFEST_NAME = "rules_manifest.json"
SIGNATURE_NAME = "rules_manifest.sig"
SIGNATURE_SCHEME = "ed25519-v1"
HASH_SCHEME = "sha256"
DANGEROUS_SHELL_RULES_NAME = "dangerous_shell_commands.yaml"
RECOVERY_COMMIT = "058c52847faeb98fc0dea6ef56ac6d4a80f5e907"
RECOVERY_SOURCE_URL = (
    "https://raw.githubusercontent.com/axjlpl2026-commits/QwenPaw/"
    f"{RECOVERY_COMMIT}/src/qwenpaw/security/tool_guard/rules/"
    f"{DANGEROUS_SHELL_RULES_NAME}"
)
RECOVERY_API_URL = (
    "https://api.github.com/repos/axjlpl2026-commits/QwenPaw/contents/"
    f"src/qwenpaw/security/tool_guard/rules/{DANGEROUS_SHELL_RULES_NAME}"
    f"?ref={RECOVERY_COMMIT}"
)
RECOVERY_HTTP_TIMEOUT = httpx.Timeout(90.0, connect=60.0, read=30.0)
RECOVERY_ATTEMPTS_PER_SOURCE = 2
RECOVERY_USER_AGENT = "QwenPaw-rule-integrity-repair/1.0"
MAX_RECOVERY_FILE_BYTES = 1024 * 1024

# Public key for the official built-in tool-rule manifest signature.
# The matching private key is used only by release tooling and is not shipped.
_PUBLIC_KEY_HEX = (
    "db31cea4a9fc8fd92d1e34a095d33699848f52bc5695f0768d697963e3966a7e"
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


@dataclass(frozen=True)
class RuleIntegrityRepairResult:
    """Result of attempting to restore the built-in rule file."""

    ok: bool
    message: str
    source_url: str
    backup_path: str | None
    integrity: RuleIntegrityResult

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["integrity"] = self.integrity.to_dict()
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


def _sha256_normalized_content(content_bytes: bytes) -> str:
    normalized = content_bytes.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_normalized_content(path.read_bytes())


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


def _load_verified_manifest(rules_dir: Path) -> dict[str, Any]:
    loaded = _load_manifest(rules_dir)
    if loaded is None:
        raise FileNotFoundError(MANIFEST_NAME)

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
    _verify_signature(rules_dir, manifest_bytes)
    return manifest


def _expected_sha256(manifest: dict[str, Any], filename: str) -> str:
    files = manifest.get("files", {})
    if not isinstance(files, dict):
        raise ValueError("manifest 'files' is not an object")

    entry = files.get(filename)
    if not isinstance(entry, dict):
        raise ValueError(f"manifest missing entry for {filename}")

    expected = entry.get("sha256")
    if not isinstance(expected, str) or not expected:
        raise ValueError(f"manifest missing sha256 for {filename}")
    return expected


def _download_raw_rule_file(client: httpx.Client) -> bytes:
    response = client.get(
        RECOVERY_SOURCE_URL,
        headers={"Accept": "text/plain"},
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.content


def _download_api_rule_file(client: httpx.Client) -> bytes:
    response = client.get(
        RECOVERY_API_URL,
        headers={"Accept": "application/vnd.github+json"},
        follow_redirects=True,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("GitHub contents response is not an object")
    if payload.get("type") != "file":
        raise ValueError(f"GitHub contents response is not a file: {payload.get('type')!r}")
    if payload.get("encoding") != "base64":
        raise ValueError(
            f"unsupported GitHub contents encoding: {payload.get('encoding')!r}",
        )

    encoded = payload.get("content")
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("GitHub contents response missing file content")
    return base64.b64decode(encoded, validate=False)


def _download_recovery_content() -> tuple[bytes, str]:
    errors: list[str] = []
    headers = {"User-Agent": RECOVERY_USER_AGENT}
    sources = (
        (RECOVERY_SOURCE_URL, _download_raw_rule_file),
        (RECOVERY_API_URL, _download_api_rule_file),
    )

    with httpx.Client(headers=headers, timeout=RECOVERY_HTTP_TIMEOUT) as client:
        for source_url, downloader in sources:
            for attempt in range(1, RECOVERY_ATTEMPTS_PER_SOURCE + 1):
                try:
                    return downloader(client), source_url
                except (
                    httpx.HTTPError,
                    ValueError,
                    json.JSONDecodeError,
                    binascii.Error,
                ) as exc:
                    errors.append(
                        f"{source_url} attempt={attempt} "
                        f"error={type(exc).__name__}: {exc}",
                    )
                    if attempt < RECOVERY_ATTEMPTS_PER_SOURCE:
                        time.sleep(attempt)

    raise RuntimeError(
        "failed to download trusted rule file; " + " | ".join(errors),
    )


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
        [DANGEROUS_SHELL_RULES_NAME],
    )


def repair_default_builtin_rule_file() -> RuleIntegrityRepairResult:
    """Restore the default dangerous shell command rules from the trusted source."""

    rules_dir = _default_rules_dir()
    target_path = rules_dir / DANGEROUS_SHELL_RULES_NAME
    source_url = RECOVERY_SOURCE_URL

    try:
        manifest = _load_verified_manifest(rules_dir)
        expected_sha256 = _expected_sha256(manifest, DANGEROUS_SHELL_RULES_NAME)

        content, source_url = _download_recovery_content()
        if len(content) > MAX_RECOVERY_FILE_BYTES:
            raise ValueError(
                f"downloaded rule file is too large: {len(content)} bytes",
            )

        actual_sha256 = _sha256_normalized_content(content)
        if actual_sha256 != expected_sha256:
            raise ValueError(
                "downloaded rule file sha256 mismatch: "
                f"expected={expected_sha256} actual={actual_sha256}",
            )

        rules_dir.mkdir(parents=True, exist_ok=True)

        fd, tmp_name = tempfile.mkstemp(
            prefix=f"{DANGEROUS_SHELL_RULES_NAME}.tmp.",
            dir=rules_dir,
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, target_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

        integrity = verify_default_builtin_rule_files()
        return RuleIntegrityRepairResult(
            ok=integrity.ok,
            message=(
                "Built-in tool guard rules were repaired."
                if integrity.ok
                else "Rule file was replaced, but integrity is still failing."
            ),
            source_url=source_url,
            backup_path=None,
            integrity=integrity,
        )
    except Exception as exc:  # pylint: disable=broad-except
        integrity = verify_default_builtin_rule_files()
        logger.error(
            "Built-in tool guard rule repair failed: source_url=%s error=%s",
            source_url,
            exc,
        )
        return RuleIntegrityRepairResult(
            ok=False,
            message=f"Failed to repair built-in tool guard rules: {exc}",
            source_url=source_url,
            backup_path=None,
            integrity=integrity,
        )
