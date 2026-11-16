"""Standalone and cross-skill import checks for #495's postmortem slice."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/signal-postmortem/scripts"
CLI = SCRIPTS / "postmortem_recorder.py"


def test_stdlib_only_help_manual_and_unavailable_provider(tmp_path):
    source = tmp_path / "fictional.json"
    source.write_text(
        json.dumps(
            {
                "signals": [
                    {
                        "signal_id": "fictional",
                        "ticker": "ZZZ",
                        "signal_date": "2026-09-01",
                        "entry_price": 100,
                        "predicted_direction": "LONG",
                        "source_skill": "fixture",
                    }
                ]
            }
        )
    )
    base = [sys.executable, "-S", str(CLI)]  # no site-packages, including requests
    help_ = subprocess.run([*base, "--help"], capture_output=True, text=True, cwd=tmp_path)
    assert help_.returncode == 0, help_.stderr
    manual = subprocess.run(
        [
            *base,
            "--signals-file",
            str(source),
            "--signal-id",
            "fictional",
            "--exit-price",
            "110",
            "--exit-date",
            "2026-09-06",
            "--output-dir",
            str(tmp_path / "manual"),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert manual.returncode == 0, manual.stderr
    record = json.loads((tmp_path / "manual/postmortems/pm_fictional.json").read_text())
    assert record["realized_returns"] == {"actual": 0.1}
    batch = subprocess.run(
        [
            *base,
            "--signals-file",
            str(source),
            "--api-key",
            "fictional-secret",
            "--output-dir",
            str(tmp_path / "batch"),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert batch.returncode == 1
    assert "Traceback" not in batch.stderr
    assert "fictional-secret" not in batch.stderr
    assert not list((tmp_path / "batch/postmortems").glob("*.json"))


def test_foreign_fmp_client_is_not_used_or_replaced(tmp_path):
    scenario = r"""
import json, sys
from pathlib import Path
from types import SimpleNamespace
directory = Path(sys.argv[1])
sys.path.insert(0, str(directory))
foreign = SimpleNamespace(FMPClient=object)
sys.modules["fmp_client"] = foreign
import postmortem_recorder as recorder
import postmortem_fmp_client as adapter
client_module = sys.modules[adapter.load_client_class().__module__]
assert Path(client_module.__file__).resolve() == directory / "fmp_client.py"
assert sys.modules["fmp_client"] is foreign
class Session:
    def __init__(self): self.headers = {}
    def get(self, url, params=None, timeout=None):
        assert url.endswith("/stable/historical-price-eod/full")
        assert params["from"] == "2026-09-01" and params["to"] == "2026-09-26"
        rows = [{"date": "2026-09-06", "close": 110}]
        return SimpleNamespace(status_code=200, json=lambda: rows, text="")
    def close(self): pass
client_module.requests.Session = Session
assert recorder.fetch_price_data("ZZZ", "2026-09-01", "2026-09-26", "fixture-only") == {"2026-09-06":110}
assert sys.modules["fmp_client"] is foreign
print("POSTMORTEM_CLIENT_OK")
"""
    completed = subprocess.run(
        [sys.executable, "-c", scenario, str(SCRIPTS)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert "POSTMORTEM_CLIENT_OK" in completed.stdout
