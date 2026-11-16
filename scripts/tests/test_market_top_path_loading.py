"""Native composite scoring remains loadable without a skill sys.path entry."""

import subprocess
import sys
from pathlib import Path


def test_market_top_composite_path_loading_needs_no_price_bar_imports():
    scorer = Path(__file__).resolve().parents[2] / "skills/market-top-detector/scripts/scorer.py"
    code = """import importlib.util,sys
spec=importlib.util.spec_from_file_location("isolated_market_top",sys.argv[1])
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
scores={key:0 for key in module.COMPONENT_WEIGHTS}
assert module.calculate_composite_score(scores)["composite_score"] == 0
result=module.calculate_composite_score(scores,{key:False for key in scores})
assert result["composite_score"] is None
assert result["risk_budget"] == "Not assessed"
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(scorer)], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr
