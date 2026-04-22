#!/bin/bash
# Thin launcher for launchd -> kill-switch/capture_sod.py
#
# Runs once at 09:20 ET Mon-Fri. Captures start-of-day Alpaca equity baseline
# so the kill-switch can compute intraday drawdown against a fixed anchor.
#
# Install:
#   sed "s|\$HOME|$HOME|g; s|\$PROJECT_DIR|$(pwd)|g" \
#     launchd/com.trade-analysis.sod-capture.plist \
#     > ~/Library/LaunchAgents/com.trade-analysis.sod-capture.plist
#   launchctl load ~/Library/LaunchAgents/com.trade-analysis.sod-capture.plist

set -euo pipefail

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:${HOME}/.local/bin:/usr/local/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.." || exit 1

command -v python3 >/dev/null 2>&1 || { echo "python3 not found" >&2; exit 1; }

# Load project .envrc (ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER)
if command -v direnv &>/dev/null && [ -f .envrc ]; then
    eval "$(direnv export bash 2>/dev/null)" || true
elif [ -f .envrc ]; then
    # shellcheck disable=SC1091
    set +u; source .envrc; set -u
fi

# Weekday check (Mon=1 .. Fri=5) in ET
ET_DOW="$(TZ=America/New_York date +%u)"
if [ "$ET_DOW" -gt 5 ]; then
    echo "[sod-capture] weekend in ET; skip" >&2
    exit 0
fi

TODAY="$(TZ=America/New_York date +%Y-%m-%d)"
mkdir -p state
exec python3 skills/kill-switch/scripts/capture_sod.py \
    --output "state/sod_${TODAY}.json"
