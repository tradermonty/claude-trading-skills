#!/bin/bash
# Thin launcher for launchd -> trade-loop-orchestrator/run_loop.py.
#
# Triggered every 5 minutes. Wrapper gates on market hours (09:45-15:45 ET,
# Mon-Fri) so opening and closing prints don't generate orders. The loop
# itself re-checks the kill-switch file before placing trades.
#
# Modes:
#   - Default:        TRADE_LOOP_MODE=execute (live order submission)
#   - Dry-run:        TRADE_LOOP_MODE=plan (compute decisions, no orders)
#
# Install:
#   sed "s|\$HOME|$HOME|g; s|\$PROJECT_DIR|$(pwd)|g" \
#     launchd/com.trade-analysis.trade-loop.plist \
#     > ~/Library/LaunchAgents/com.trade-analysis.trade-loop.plist
#   launchctl load ~/Library/LaunchAgents/com.trade-analysis.trade-loop.plist

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
ET_HHMM="$(TZ=America/New_York date +%H%M)"

if [ "$ET_DOW" -gt 5 ]; then exit 0; fi
if [ "$ET_HHMM" -lt 0945 ] || [ "$ET_HHMM" -gt 1545 ]; then exit 0; fi

# Refuse to trade if kill-switch state file says TRIPPED.
KS_FILE="state/kill_switch_status.json"
if [ -f "$KS_FILE" ]; then
    if grep -q '"status": *"TRIPPED"' "$KS_FILE"; then
        echo "[trade-loop] kill-switch TRIPPED; skipping iteration" >&2
        exit 0
    fi
fi

MODE="${TRADE_LOOP_MODE:-execute}"
mkdir -p state/loop logs

exec python3 skills/trade-loop-orchestrator/scripts/run_loop.py \
    --mode "$MODE" \
    --output state/loop/
