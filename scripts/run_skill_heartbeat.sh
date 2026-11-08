#!/bin/bash
# Independent watchdog for the improvement and generation success heartbeats.
# Install all maintenance agents: python3 scripts/install_launchd.py
# Add --load to activate schedules.
# Defaults to local macOS notifications; SKILL_LOOP_NOTIFY=off disables delivery.
# Does not source .envrc, modify state, run scoring, or invoke the monitored jobs.

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:${HOME}/.local/bin:/usr/local/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)" || exit 1
export SKILL_LOOP_NOTIFY="${SKILL_LOOP_NOTIFY:-macos}"
command -v python3 >/dev/null 2>&1 || { echo "Heartbeat check unavailable: python3 not found." >&2; exit 1; }
python3 "${SCRIPT_DIR}/job_monitor.py" --notify-heartbeat --project-root "${PROJECT_ROOT}"
