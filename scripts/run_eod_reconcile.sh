#!/bin/bash
# Thin launcher for launchd -> eod-reconciliation/run_eod.py.
#
# Runs once at 16:30 ET Mon-Fri. Reconciles the day's loop decisions against
# Alpaca fills, attributes P&L, closes matched theses, and triggers postmortems.
#
# Install:
#   sed "s|\$HOME|$HOME|g; s|\$PROJECT_DIR|$(pwd)|g" \
#     launchd/com.trade-analysis.eod-reconcile.plist \
#     > ~/Library/LaunchAgents/com.trade-analysis.eod-reconcile.plist
#   launchctl load ~/Library/LaunchAgents/com.trade-analysis.eod-reconcile.plist

set -euo pipefail

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:${HOME}/.local/bin:/usr/local/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.." || exit 1

command -v python3 >/dev/null 2>&1 || { echo "python3 not found" >&2; exit 1; }

if command -v direnv &>/dev/null && [ -f .envrc ]; then
    eval "$(direnv export bash 2>/dev/null)" || true
elif [ -f .envrc ]; then
    # shellcheck disable=SC1091
    set +u; source .envrc; set -u
fi

ET_DOW="$(TZ=America/New_York date +%u)"
if [ "$ET_DOW" -gt 5 ]; then
    echo "[eod-reconcile] weekend in ET; skip" >&2
    exit 0
fi

mkdir -p reports/eod logs
exec python3 skills/eod-reconciliation/scripts/run_eod.py \
    --output-dir reports/eod/
