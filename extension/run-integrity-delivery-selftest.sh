#!/usr/bin/env sh
# Run all Integrity Protection delivery self-test nets (wiring + backend + frontend).
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec python3 "$SCRIPT_DIR/run-integrity-delivery-selftest.py" "$@"
