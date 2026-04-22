#!/usr/bin/env bash
# Install the official Alpaca MCP server and register it with Claude Desktop.
#
# What this does:
#   1. Ensures `uv` (Astral's Python package runner) is installed. The Alpaca
#      MCP server is launched as `uvx alpaca-mcp-server`.
#   2. Reads API keys from the repo's .env file.
#   3. Safely merges an "alpaca" entry into
#      ~/Library/Application Support/Claude/claude_desktop_config.json,
#      backing up the existing file first.
#   4. Tells you to restart Claude Desktop.
#
# Idempotent: running it twice is safe — it overwrites only the "alpaca" key
# inside mcpServers and leaves every other server intact.
#
# Source: https://github.com/alpacahq/alpaca-mcp-server

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
CLAUDE_CONFIG_DIR="${HOME}/Library/Application Support/Claude"
CLAUDE_CONFIG="${CLAUDE_CONFIG_DIR}/claude_desktop_config.json"

# ---- 1. Load keys from .env --------------------------------------------------
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "error: ${ENV_FILE} not found. Run the project setup first." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

if [[ -z "${ALPACA_API_KEY:-}" || -z "${ALPACA_SECRET_KEY:-}" ]]; then
  echo "error: ALPACA_API_KEY or ALPACA_SECRET_KEY missing in ${ENV_FILE}" >&2
  exit 1
fi

# Map our ALPACA_PAPER (true/false) to Alpaca MCP's ALPACA_PAPER_TRADE (true/false).
PAPER_FLAG="${ALPACA_PAPER:-true}"

# ---- 2. Ensure `uv` is installed --------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Installing via Astral's official installer..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # The installer places uv in ~/.local/bin or ~/.cargo/bin depending on version.
  export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"
  if ! command -v uv >/dev/null 2>&1; then
    echo "error: uv install appeared to succeed but 'uv' is still not on PATH." >&2
    echo "       Add ~/.local/bin to your PATH (in ~/.zshrc), restart your shell, and rerun." >&2
    exit 1
  fi
fi

UV_PATH="$(command -v uv)"
UVX_PATH="$(command -v uvx || true)"
if [[ -z "${UVX_PATH}" ]]; then
  # uvx ships alongside uv; if it's missing something is wrong.
  echo "error: uvx not found even though uv is at ${UV_PATH}." >&2
  exit 1
fi

echo "uv:  ${UV_PATH}"
echo "uvx: ${UVX_PATH}"

# ---- 3. Pre-cache the Alpaca MCP server so first launch is fast -------------
echo "Pre-fetching alpaca-mcp-server from PyPI (one-time cache)..."
"${UVX_PATH}" --from alpaca-mcp-server python -c "import sys; sys.exit(0)" >/dev/null 2>&1 || {
  # Not fatal — uvx will fetch on first use by Claude Desktop anyway.
  echo "warn: pre-fetch failed. Claude Desktop will fetch it on first launch instead." >&2
}

# ---- 4. Merge config into claude_desktop_config.json ------------------------
mkdir -p "${CLAUDE_CONFIG_DIR}"

if [[ -f "${CLAUDE_CONFIG}" ]]; then
  BACKUP="${CLAUDE_CONFIG}.bak.$(date +%Y%m%d_%H%M%S)"
  cp "${CLAUDE_CONFIG}" "${BACKUP}"
  echo "Backed up existing config to: ${BACKUP}"
else
  echo "{}" > "${CLAUDE_CONFIG}"
  echo "Created new config file: ${CLAUDE_CONFIG}"
fi

python3 - "${CLAUDE_CONFIG}" "${UVX_PATH}" "${ALPACA_API_KEY}" "${ALPACA_SECRET_KEY}" "${PAPER_FLAG}" <<'PY'
import json, sys
from pathlib import Path

config_path, uvx_path, api_key, secret_key, paper_flag = sys.argv[1:6]
p = Path(config_path)

try:
    data = json.loads(p.read_text()) if p.read_text().strip() else {}
except json.JSONDecodeError as e:
    sys.exit(f"error: existing {p} is not valid JSON ({e}). Fix or delete it, then rerun.")

data.setdefault("mcpServers", {})
data["mcpServers"]["alpaca"] = {
    "command": uvx_path,
    "args": ["alpaca-mcp-server"],
    "env": {
        "ALPACA_API_KEY": api_key,
        "ALPACA_SECRET_KEY": secret_key,
        "ALPACA_PAPER_TRADE": "true" if paper_flag.lower() == "true" else "false",
    },
}

p.write_text(json.dumps(data, indent=2) + "\n")
print(f"Wrote alpaca MCP entry to {p}")
PY

# ---- 5. Done ----------------------------------------------------------------
cat <<EOF

Alpaca MCP server registered with Claude Desktop.

Next steps:
  1. Fully quit Claude Desktop (Cmd-Q — not just close the window).
  2. Relaunch Claude Desktop.
  3. In any new chat, ask: "What Alpaca tools do you have?"
     You should see tools with names starting with alpaca__ (e.g. alpaca__get_account).
  4. Try: "Show my Alpaca paper account balance."

If it doesn't show up, check the logs at:
  ~/Library/Logs/Claude/mcp.log
  ~/Library/Logs/Claude/mcp-server-alpaca.log
EOF
