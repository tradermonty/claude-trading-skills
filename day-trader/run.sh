#!/usr/bin/env bash
# Start the day trading agent locally.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d .venv ]]; then
  echo "Creating virtualenv..."
  python3 -m venv .venv
fi

source .venv/bin/activate

if ! python -c "import alpaca" 2>/dev/null; then
  echo "Installing dependencies..."
  pip install -q --upgrade pip
  pip install -q -r requirements.txt
fi

if [[ ! -f .env ]]; then
  echo "ERROR: .env missing. Copy .env.example and fill in ALPACA_API_KEY/SECRET." >&2
  exit 1
fi

echo "Opening http://127.0.0.1:8787  (Ctrl+C to quit)"
python main.py
