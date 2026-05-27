"""Env loader for TraderMonty API keys.

Convention:
    Keys live in ~/.claude/secrets/tradermonty.env as shell-style assignments:
        export FOO_API_KEY="value"  # pragma: allowlist secret
        BAR_API_KEY=value  # pragma: allowlist secret

    This module parses that file and exposes get_api_key(name) without ever
    echoing values. Already-set env vars take precedence (12-factor).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

SECRETS_PATH = Path.home() / ".claude" / "secrets" / "tradermonty.env"

_LOADED = False
_VALUE_RE = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$")
# "Provider  :Marketeaux" / "API Key   :abc123" block format
_PROVIDER_RE = re.compile(r"^\s*Provider\s*:\s*(.+?)\s*$", re.IGNORECASE)
_PROVIDER_KEY_RE = re.compile(r"^\s*API Key\s*:\s*(.+?)\s*$", re.IGNORECASE)

# Normalized env-var names for free-text provider blocks
_PROVIDER_NAME_MAP = {
    "marketeaux": "MARKETAUX_API_KEY",
    "newsdata io": "NEWSDATA_API_KEY",
    "newsdata": "NEWSDATA_API_KEY",
    "apify": "APIFY_API_KEY",
}


def load_env(path: Path = SECRETS_PATH, override: bool = False) -> dict[str, str]:
    """Parse the secrets file and inject keys into os.environ.

    Args:
        path: location of the env file (default: ~/.claude/secrets/tradermonty.env)
        override: if True, replace existing env vars; if False, keep them

    Returns:
        dict of {key: "***REDACTED***"} (values never returned for security)
    """
    global _LOADED
    if not path.exists():
        return {}

    keys_seen: dict[str, str] = {}
    pending_provider: str | None = None  # for "Provider :X / API Key :Y" blocks
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            # Skip comments and blanks
            if not line or line.lstrip().startswith("#"):
                continue

            # Provider-block format (multi-line)
            pm = _PROVIDER_RE.match(line)
            if pm:
                pending_provider = pm.group(1).strip().lower()
                continue
            km = _PROVIDER_KEY_RE.match(line)
            if km and pending_provider:
                val = km.group(1).strip()
                env_name = _PROVIDER_NAME_MAP.get(
                    pending_provider,
                    pending_provider.upper().replace(" ", "_") + "_API_KEY",
                )
                pending_provider = None
                if val and (override or env_name not in os.environ):
                    os.environ[env_name] = val
                    keys_seen[env_name] = "***REDACTED***"
                continue

            m = _VALUE_RE.match(line)
            if not m:
                continue
            key, val = m.group(1), m.group(2)
            # Strip surrounding quotes
            if (val.startswith('"') and val.endswith('"')) or (
                val.startswith("'") and val.endswith("'")
            ):
                val = val[1:-1]
            # Strip whitespace inside (rare, but Marketeaux line had a leading space)
            val = val.strip()
            if not val:
                continue
            if override or key not in os.environ:
                os.environ[key] = val
            keys_seen[key] = "***REDACTED***"
    _LOADED = True
    return keys_seen


def get_api_key(name: str, *, required: bool = True) -> str | None:
    """Fetch an API key by name. Auto-loads the secrets file on first call.

    Args:
        name: env var name (e.g. "POLYGON_API_KEY")
        required: raise RuntimeError if missing (default True)

    Returns:
        the key value, or None if not required and missing

    Raises:
        RuntimeError: if required=True and the key is not set
    """
    global _LOADED
    if not _LOADED:
        load_env()
    val = os.environ.get(name)
    if not val:
        if required:
            raise RuntimeError(
                f"Missing API key {name}. Set it in {SECRETS_PATH} "
                f"or export {name}=... in your shell."
            )
        return None
    return val


if __name__ == "__main__":
    # CLI: show which keys are loaded (names only, never values)
    loaded = load_env()
    if not loaded:
        print(f"No keys loaded from {SECRETS_PATH}")
    else:
        print(f"Loaded {len(loaded)} keys from {SECRETS_PATH}:")
        for k in sorted(loaded):
            print(f"  {k}")
