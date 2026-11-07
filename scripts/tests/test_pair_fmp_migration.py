"""Fresh-process pair adapters must use their sibling despite a foreign client."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("script", ["find_pairs", "analyze_spread"])
@pytest.mark.parametrize("recorded", ["sparse", "contract"])
def test_pair_adapters_keep_their_own_generated_client(script, recorded):
    scenario = r"""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

directory = Path(sys.argv[1])
sys.path.insert(0, str(directory))
foreign = SimpleNamespace(FMPClient=object)
sys.modules["fmp_client"] = foreign
spec = importlib.util.spec_from_file_location("pair_adapter", directory / (sys.argv[2] + ".py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
client_module = sys.modules[module.FMPClient.__module__]
assert Path(client_module.__file__).resolve() == directory / "fmp_client.py"
assert sys.modules["fmp_client"] is foreign
if sys.argv[3] == "contract":
    payload = json.loads((directory.parents[2] / "config/provider-contracts/fmp/historical-price-eod-full.v1.json").read_text())["fixture"]
    symbol = "AAPL"
else:
    payload = [{"symbol":"AAA", "date":"2001-01-02", "close":100.0}]
    symbol = "AAA"
class Session:
    def __init__(self): self.headers = {}
    def get(self, url, params=None, timeout=None):
        assert params == {"symbol": symbol}
        if url.endswith("/stable/historical-price-eod/dividend-adjusted"):
            # Unavailable on this key: the adapter must fall back to the full endpoint.
            return SimpleNamespace(status_code=402, json=lambda: {}, text="")
        assert url.endswith("/stable/historical-price-eod/full")
        return SimpleNamespace(status_code=200, json=lambda: payload, text="")
client_module.requests.Session = Session
series = module.fetch_historical_prices(symbol, "fixture-only", lookback_days=1)
assert series.tolist() == [payload[0].get("adjClose") or payload[0]["close"]]
print("PAIR_CLIENT_OK")
"""
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            scenario,
            str(ROOT / "skills/pair-trade-screener/scripts"),
            script,
            recorded,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert "PAIR_CLIENT_OK" in completed.stdout
