"""Load the required statistical dependency with an actionable error."""

from __future__ import annotations

from pathlib import Path

INSTALL_COMMAND = "uv run --with 'statsmodels>=0.14,<0.15' python"
REQUIREMENTS_PATH = Path(__file__).resolve().parents[1] / "requirements.txt"


class MissingDependencyError(RuntimeError):
    """statsmodels is not installed; CLIs map this to exit status 2."""


def require_statsmodels():
    """Return the statsmodels tools used by the pair-trading scripts."""
    try:
        from statsmodels.tsa.ar_model import AutoReg
        from statsmodels.tsa.stattools import adfuller
    except ImportError as exc:
        raise MissingDependencyError(
            "statsmodels>=0.14,<0.15 is required for cointegration analysis. "
            f"Install this skill's dependencies: pip install -r {REQUIREMENTS_PATH} "
            f"or run the command with: {INSTALL_COMMAND} <script> [arguments]"
        ) from exc
    return AutoReg, adfuller
