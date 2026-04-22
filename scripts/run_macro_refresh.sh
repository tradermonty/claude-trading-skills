#!/bin/bash
# Thin launcher for launchd -> macro-indicator-dashboard pipeline.
#
# Runs once at 07:00 ET Mon-Fri before the open. Refreshes FRED-sourced
# macro indicators, recomputes the regime score, and regenerates the
# dashboard so the trade loop has fresh inputs by 09:45 ET.
#
# Pipeline:
#   1. fetch_fred_data.py  -> state/macro/macro_raw_<date>.json
#   2. compute_regime.py   -> state/macro/regime_<date>.json
#   3. generate_dashboard  -> reports/macro_dashboard_<date>.{md,json}
#
# Install:
#   sed "s|\$HOME|$HOME|g; s|\$PROJECT_DIR|$(pwd)|g" \
#     launchd/com.trade-analysis.macro-refresh.plist \
#     > ~/Library/LaunchAgents/com.trade-analysis.macro-refresh.plist
#   launchctl load ~/Library/LaunchAgents/com.trade-analysis.macro-refresh.plist

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
    echo "[macro-refresh] weekend in ET; skip" >&2
    exit 0
fi

if [ -z "${FRED_API_KEY:-}" ]; then
    echo "[macro-refresh] FRED_API_KEY not set; aborting" >&2
    exit 1
fi

TODAY="$(TZ=America/New_York date +%Y-%m-%d)"
mkdir -p state/macro reports logs

RAW="state/macro/macro_raw_${TODAY}.json"
REGIME="state/macro/regime_${TODAY}.json"

# Find yesterday's regime file for trend comparison (if it exists).
PREV_REGIME=""
for d in $(ls -1t state/macro/regime_*.json 2>/dev/null | grep -v "regime_${TODAY}\.json" | head -1); do
    PREV_REGIME="$d"
done

python3 skills/macro-indicator-dashboard/scripts/fetch_fred_data.py \
    --output "$RAW"

if [ -n "$PREV_REGIME" ]; then
    python3 skills/macro-indicator-dashboard/scripts/compute_regime.py \
        --input "$RAW" --output "$REGIME" --previous "$PREV_REGIME"
else
    python3 skills/macro-indicator-dashboard/scripts/compute_regime.py \
        --input "$RAW" --output "$REGIME"
fi

python3 skills/macro-indicator-dashboard/scripts/generate_dashboard.py \
    --input "$REGIME" --output-dir reports/
