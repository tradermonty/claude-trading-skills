#!/usr/bin/env bash
# POSIX convenience wrapper. The Python entry point is cross-platform.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --extra dev python "${SCRIPT_DIR}/run_all_tests.py" "$@"
