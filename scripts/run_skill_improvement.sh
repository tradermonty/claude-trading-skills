#!/bin/bash
# Thin launcher for launchd → run_skill_improvement_loop.py
#
# Install as launchd agent:
#   cp launchd/com.trade-analysis.skill-improvement.plist ~/Library/LaunchAgents/
#   launchctl load ~/Library/LaunchAgents/com.trade-analysis.skill-improvement.plist
#   launchctl list | grep skill-improvement
#
# Manual dry-run test:
#   launchctl start com.trade-analysis.skill-improvement
#   # or: bash scripts/run_skill_improvement.sh --dry-run

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:${HOME}/.local/bin:/usr/local/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.." || exit 1
python3 scripts/run_skill_improvement_loop.py "$@"
