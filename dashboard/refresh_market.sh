#!/bin/sh
# Writes fresh market reports into reports/ for the dashboard.
# Runs inside the dashboard image (see the "refresh" service in compose.yaml).
# Breadth, uptrend and exposure need no API key. VCP runs only when
# RUN_VCP=true and FMP_API_KEY are both set in .env. The drawdown circuit
# breaker runs when CB_ACCOUNT_SIZE is set.
#
#   refresh_market.sh           everything (weekday 4:20 PM cron)
#   refresh_market.sh circuit   only the circuit breaker (weekday morning cron)
set -u
cd /repo || exit 1
mkdir -p reports
status=0

run_circuit() {
  if [ -z "${CB_ACCOUNT_SIZE:-}" ]; then
    echo "== circuit breaker: skipped (set CB_ACCOUNT_SIZE in .env)"
    return 0
  fi
  echo "== circuit breaker"
  set -- --state-dir state/theses --account-size "$CB_ACCOUNT_SIZE" --output-dir reports
  [ -n "${CB_MAX_DAILY_LOSS_PCT:-}" ] && set -- "$@" --max-daily-loss-pct "$CB_MAX_DAILY_LOSS_PCT"
  [ -n "${CB_LOSING_STREAK_N:-}" ] && set -- "$@" --losing-streak-n "$CB_LOSING_STREAK_N"
  [ -n "${CB_COOLDOWN_HOURS:-}" ] && set -- "$@" --cooldown-hours "$CB_COOLDOWN_HOURS"
  [ -n "${CB_WEEKLY_DRAWDOWN_PCT:-}" ] && set -- "$@" --weekly-drawdown-pct "$CB_WEEKLY_DRAWDOWN_PCT"
  [ -n "${CB_MONTHLY_DRAWDOWN_PCT:-}" ] && set -- "$@" --monthly-drawdown-pct "$CB_MONTHLY_DRAWDOWN_PCT"
  python skills/drawdown-circuit-breaker/scripts/check_circuit_breaker.py "$@" || return 1
}

if [ "${1:-}" = "circuit" ]; then
  run_circuit || status=1
  exit $status
fi

echo "== market breadth"
python skills/market-breadth-analyzer/scripts/market_breadth_analyzer.py --output-dir reports || status=1

echo "== uptrend ratio"
python skills/uptrend-analyzer/scripts/uptrend_analyzer.py --output-dir reports || status=1

newest() { ls -1t reports/"$1"*.json 2>/dev/null | head -n 1; }
BREADTH=$(newest market_breadth_)
UPTREND=$(newest uptrend_analysis_)

echo "== exposure posture"
if [ -n "$BREADTH" ] && [ -n "$UPTREND" ]; then
  python skills/exposure-coach/scripts/calculate_exposure.py \
    --breadth "$BREADTH" --uptrend "$UPTREND" --output-dir reports || status=1
else
  echo "skipped: breadth or uptrend report missing" >&2
  status=1
fi

if [ "${RUN_VCP:-false}" = "true" ] && [ -n "${FMP_API_KEY:-}" ]; then
  echo "== VCP screener"
  python skills/vcp-screener/scripts/screen_vcp.py --output-dir reports || status=1
fi

run_circuit || status=1

exit $status
