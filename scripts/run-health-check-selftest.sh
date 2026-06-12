#!/usr/bin/env bash
# Run Health Check self-test net (architecture + backend + frontend).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT"
exec python3 "$SCRIPT_DIR/run-health-check-selftest.py" "$@"
