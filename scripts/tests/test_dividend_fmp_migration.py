"""Batch B exercises real domain adapters + generated HTTP in isolated processes."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    "value-dividend-screener": "screen_dividend_stocks",
    "dividend-growth-pullback-screener": "screen_dividend_growth_rsi",
    "kanchi-dividend-sop": "build_entry_signals",
}

# Isolation matters: each standalone package intentionally imports fmp_client
# under the same module name. The subprocess imports exactly the selected bundle.
SCENARIOS = r"""
import sys
sys.path.insert(0, sys.argv[1])
from _dividend_fmp_scenarios import run_scenarios
run_scenarios(sys.argv[2], sys.argv[3])
"""


@pytest.mark.parametrize("skill,module_name", TARGETS.items())
def test_domain_adapters_use_shared_transport(skill: str, module_name: str):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            SCENARIOS,
            str(ROOT / "scripts/tests"),
            str(ROOT / "skills" / skill / "scripts"),
            module_name,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "BATCH_B_TRANSPORT_OK" in result.stdout
