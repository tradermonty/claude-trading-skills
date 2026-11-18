#!/bin/sh
# Writes fresh market reports into reports/ for the dashboard.
# Runs inside the dashboard image (see the "refresh" service in compose.yaml).
# Breadth, uptrend and exposure need no API key. VCP runs only when
# RUN_VCP=true and FMP_API_KEY are both set in .env.
set -u
cd /repo || exit 1
mkdir -p reports
status=0

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

exit $status
