# -*- coding: utf-8 -*-
"""Generate the signed manifest for built-in tool guard rules.

Usage:
    python scripts/update_tool_rule_manifest.py \
      --private-key-file /secure/path/ed25519_private.pem

Or set:
    QWENPAW_RULE_SIGNING_PRIVATE_KEY_FILE=/secure/path/ed25519_private.pem
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

RULES_DIR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "qwenpaw"
    / "security"
    / "tool_guard"
    / "rules"
)
RULE_FILES = ("dangerous_shell_commands.yaml",)
MANIFEST_NAME = "rules_manifest.json"
SIGNATURE_NAME = "rules_manifest.sig"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(data: dict) -> bytes:
    return json.dumps(
        data,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _load_private_key(path: Path) -> Ed25519PrivateKey:
    raw = path.read_bytes()
    key = serialization.load_pem_private_key(raw, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("private key must be an Ed25519 private key")
    return key


def build_manifest() -> dict:
    files = {}
    for filename in RULE_FILES:
        rule_path = RULES_DIR / filename
        if not rule_path.is_file():
            raise FileNotFoundError(rule_path)
        files[filename] = {
            "required": True,
            "sha256": _sha256_file(rule_path),
        }
    return {
        "files": files,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hash_scheme": "sha256",
        "schema_version": 1,
        "signature_scheme": "ed25519-v1",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--private-key-file",
        default=os.environ.get("QWENPAW_RULE_SIGNING_PRIVATE_KEY_FILE"),
        help=(
            "Path to the Ed25519 PEM private key. Defaults to "
            "QWENPAW_RULE_SIGNING_PRIVATE_KEY_FILE."
        ),
    )
    args = parser.parse_args()
    if not args.private_key_file:
        raise SystemExit(
            "Missing --private-key-file or "
            "QWENPAW_RULE_SIGNING_PRIVATE_KEY_FILE.",
        )

    private_key = _load_private_key(Path(args.private_key_file))
    manifest_bytes = _canonical_json(build_manifest())
    signature = private_key.sign(manifest_bytes)

    (RULES_DIR / MANIFEST_NAME).write_bytes(manifest_bytes)
    (RULES_DIR / SIGNATURE_NAME).write_text(
        signature.hex() + "\n",
        encoding="ascii",
    )
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    print(f"public_key_hex={public_key.hex()}")
    print(f"manifest={RULES_DIR / MANIFEST_NAME}")
    print(f"signature={RULES_DIR / SIGNATURE_NAME}")


if __name__ == "__main__":
    main()
