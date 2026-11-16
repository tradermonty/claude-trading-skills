"""Missing ``requests`` on the live FMP path exits 2 with a requirements.txt hint (#497)."""

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "run_20pct_study.py"
spec = importlib.util.spec_from_file_location("run_20pct_study_missing_dep", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_live_fmp_path_without_requests_exits_2(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(mod, "requests", None)
    rc = mod.main(
        [
            "scan",
            "--symbols",
            "AAPL",
            "--state-file",
            str(tmp_path / "state.jsonl"),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "ERROR: requests library not found" in captured.err
    assert "pip install -r" in captured.err
    assert "requirements.txt" in captured.err


def test_other_runtime_errors_still_exit_1(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(mod, "requests", object())
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    rc = mod.main(
        [
            "scan",
            "--symbols",
            "AAPL",
            "--state-file",
            str(tmp_path / "state.jsonl"),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 1
    assert "FMP API key required" in capsys.readouterr().err
