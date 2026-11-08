#!/bin/bash
# Thin launcher for launchd -> run_skill_generation_pipeline.py
#
# Install all maintenance agents from the repository root:
#   python3 scripts/install_launchd.py
# Add --load to activate schedules.
# Existing customized plists are preserved; see docs/dev/maintenance-runbook.md.
#
# Manual test:
#   launchctl start com.trade-analysis.skill-generation-weekly
#   # or: bash scripts/run_skill_generation.sh --mode weekly --dry-run

# Allow claude -p subprocess calls even when launched from a Claude Code terminal
unset CLAUDECODE

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:${HOME}/.local/bin:/usr/local/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Capture setup and orchestrator failures without replacing their exit status.
notify_on_exit() {
    local result=$?
    trap - EXIT
    if [ "$result" -ne 0 ] && [ -n "${SKILL_LOOP_NOTIFY:-}" ]; then
        if command -v python3 >/dev/null 2>&1; then
            python3 "${SCRIPT_DIR}/job_monitor.py" --notify-failure "$MONITOR_JOB" --exit-code "$result" || true
        else
            echo "Automation notification unavailable: python3 not found." >&2
        fi
    fi
    exit "$result"
}
MONITOR_JOB=generation
monitor_expect_mode=false
for monitor_arg in "$@"; do
    if [ "$monitor_expect_mode" = true ]; then
        case "$monitor_arg" in daily|weekly) MONITOR_JOB="generation-${monitor_arg}" ;; esac
        monitor_expect_mode=false
    fi
    case "$monitor_arg" in
        --mode) monitor_expect_mode=true ;;
        --mode=daily) MONITOR_JOB=generation-daily ;;
        --mode=weekly) MONITOR_JOB=generation-weekly ;;
    esac
done
trap notify_on_exit EXIT
cd "${SCRIPT_DIR}/.." || exit 1

command -v python3 >/dev/null 2>&1 || { echo "python3 not found" >&2; exit 1; }

# Load project-level .envrc (sets GH_TOKEN for the correct GitHub account)
if command -v direnv &>/dev/null && [ -f .envrc ]; then
    eval "$(direnv export bash 2>/dev/null)"
fi

python3 scripts/run_skill_generation_pipeline.py "$@"
