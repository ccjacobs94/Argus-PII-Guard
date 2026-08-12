#!/usr/bin/env bash
# Argus PII Guard Unix Installer Launcher Script (Linux & macOS)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "========================================================"
echo "  Argus PII Guard Native Installer Launcher"
echo "========================================================"

if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "[ERROR] Python 3 is required to run the Argus PII Guard installer."
    exit 1
fi

"$PYTHON_BIN" "$SCRIPT_DIR/native_installer.py" "$@"
