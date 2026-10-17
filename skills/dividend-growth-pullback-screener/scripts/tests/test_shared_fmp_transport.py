"""Exercise the real generated HTTP client in this skill's coverage row."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts/tests"))
from _dividend_fmp_scenarios import run_scenarios


def test_generated_transport_and_domain_adapters():
    run_scenarios(
        ROOT / "skills/dividend-growth-pullback-screener/scripts", "screen_dividend_growth_rsi"
    )
