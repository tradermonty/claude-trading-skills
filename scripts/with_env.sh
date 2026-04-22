#!/usr/bin/env bash
# Convenience wrapper: source .env (if present) and run the passed command.
#
# Usage:
#   scripts/with_env.sh python3 skills/portfolio-manager/scripts/check_alpaca_connection.py
#   scripts/with_env.sh python3 skills/earnings-calendar/scripts/fetch_earnings_fmp.py
#
# Rationale: the repo's scripts read API keys from environment variables
# (FMP_API_KEY, FINVIZ_API_KEY, ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER).
# Keeping secrets in .env (gitignored) instead of your shell rc file avoids
# leaking them into every shell you open.

set -euo pipefail

# Resolve repo root as the directory containing this script's parent.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
else
  echo "warn: ${ENV_FILE} not found — running without API keys" >&2
fi

if [[ $# -eq 0 ]]; then
  echo "usage: $0 <command> [args...]" >&2
  exit 2
fi

exec "$@"
