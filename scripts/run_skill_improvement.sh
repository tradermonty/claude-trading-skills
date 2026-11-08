#!/bin/bash
# Thin launcher for launchd → run_skill_improvement_loop.py
#
# The loop refuses to run on a dirty tree or off main, so it must never run
# against the maintainer's working tree — a normal day of editing blocks it.
# Instead it runs in a dedicated checkout that this launcher resets to
# origin/main on every invocation. logs/ and reports/ are symlinked back to
# the primary repo so round-robin state and summaries stay in one place.
#
# Install all maintenance agents from the repository root:
#   python3 scripts/install_launchd.py
# Add --load to activate schedules.
# Existing customized plists are preserved; see docs/dev/maintenance-runbook.md.
#
# Manual dry-run test:
#   bash scripts/run_skill_improvement.sh --dry-run
#
# Override the automation checkout location with SKILL_LOOP_CHECKOUT.

set -o pipefail

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
MONITOR_JOB=improvement
trap notify_on_exit EXIT
PRIMARY_REPO="$(cd "${SCRIPT_DIR}/.." && pwd)"
CHECKOUT="${SKILL_LOOP_CHECKOUT:-${HOME}/.local/share/claude-trading-skills-bot}"

command -v python3 >/dev/null 2>&1 || { echo "python3 not found" >&2; exit 1; }
command -v git >/dev/null 2>&1 || { echo "git not found" >&2; exit 1; }

# Load project-level .envrc (sets GH_TOKEN for the correct GitHub account).
# It is gitignored, so it lives only in the primary repo.
cd "${PRIMARY_REPO}" || exit 1
if command -v direnv &>/dev/null && [ -f .envrc ]; then
    eval "$(direnv export bash 2>/dev/null)"
fi

ORIGIN_URL="$(git -C "${PRIMARY_REPO}" remote get-url origin)" || {
    echo "cannot resolve origin URL from ${PRIMARY_REPO}" >&2
    exit 1
}

if [ ! -d "${CHECKOUT}/.git" ]; then
    echo "Creating automation checkout at ${CHECKOUT}"
    mkdir -p "$(dirname "${CHECKOUT}")" || exit 1
    git clone "${ORIGIN_URL}" "${CHECKOUT}" || {
        echo "clone failed: ${ORIGIN_URL} -> ${CHECKOUT}" >&2
        exit 1
    }
fi

# Reset the automation checkout to a pristine origin/main. `git clean -fd`
# deliberately omits -x so gitignored logs/, reports/ and state/ survive.
git -C "${CHECKOUT}" fetch origin --prune --quiet || {
    echo "fetch failed in ${CHECKOUT}" >&2
    exit 1
}
git -C "${CHECKOUT}" checkout -B main origin/main --quiet || exit 1
git -C "${CHECKOUT}" reset --hard origin/main --quiet || exit 1
git -C "${CHECKOUT}" clean -fd --quiet || exit 1

# Keep loop state and summaries in the primary repo so history is continuous
# and the maintainer reads one set of files.
for shared in logs reports; do
    if [ ! -L "${CHECKOUT}/${shared}" ]; then
        rm -rf "${CHECKOUT:?}/${shared}"
        mkdir -p "${PRIMARY_REPO}/${shared}"
        ln -s "${PRIMARY_REPO}/${shared}" "${CHECKOUT}/${shared}" || exit 1
    fi
done

cd "${CHECKOUT}" || exit 1
python3 "${CHECKOUT}/scripts/run_skill_improvement_loop.py" --project-root "${CHECKOUT}" "$@"
