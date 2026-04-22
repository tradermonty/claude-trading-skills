#!/bin/bash
# Thin launcher for launchd -> kill-switch/check_limits.py watchdog.
#
# Triggered every 2 minutes by launchd. The wrapper itself gates on
# market hours (09:30-16:00 ET, Mon-Fri) so the plist can stay simple.
# If a hard-limit breach is detected, check_limits.py shells out to
# alpaca-executor/flatten_all.py automatically.
#
# Install:
#   sed "s|\$HOME|$HOME|g; s|\$PROJECT_DIR|$(pwd)|g" \
#     launchd/com.trade-analysis.kill-switch.plist \
#     > ~/Library/LaunchAgents/com.trade-analysis.kill-switch.plist
#   launchctl load ~/Library/LaunchAgents/com.trade-analysis.kill-switch.plist

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

# Weekdays only, 09:30-16:00 ET
if [ "$ET_DOW" -gt 5 ]; then exit 0; fi
if [ "$ET_HHMM" -lt 0930 ] || [ "$ET_HHMM" -gt 1600 ]; then exit 0; fi

TODAY="$(TZ=America/New_York date +%Y-%m-%d)"
SOD_FILE="state/sod_${TODAY}.json"
mkdir -p state logs

if [ ! -f "$SOD_FILE" ]; then
    echo "[kill-switch] SOD file missing: $SOD_FILE - skipping watchdog tick" >&2
    exit 0
fi

python3 skills/kill-switch/scripts/check_limits.py \
    --sod "$SOD_FILE" \
    --output state/kill_switch_status.json
rc=$?

# Exit codes:
#   0 OK, 1 TRIPPED (flatten fired), 2 WARN (soft), 3 UNKNOWN (alpaca down)
# launchd treats non-zero as a failure + restart candidate; swallow non-critical
# codes so the watchdog schedule stays clean.
case "$rc" in
    0|2) exit 0 ;;
    1)
        echo "[kill-switch] TRIPPED at $(date -u +%FT%TZ) - see state/kill_switch_status.json" >&2
        exit 0
        ;;
    3)
        echo "[kill-switch] UNKNOWN (alpaca unreachable) at $(date -u +%FT%TZ)" >&2
        exit 0
        ;;
    *)
        exit "$rc"
        ;;
esac
