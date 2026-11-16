"""YAML input without PyYAML exits 2 with a requirements.txt hint; JSON still works (#497)."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPT_DIR))

import review_trade_performance as rpc  # noqa: E402


def test_yaml_input_without_pyyaml_exits_2(monkeypatch, capsys, tmp_path):
    record = tmp_path / "record.yaml"
    record.write_text("trade_id: t1\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "yaml", None)  # `import yaml` raises ImportError
    rc = rpc.main(["--input", str(record), "--output-dir", str(tmp_path / "out")])
    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "ERROR: PyYAML library not found" in captured.err
    assert "pip install -r" in captured.err
    assert "requirements.txt" in captured.err
    assert not (tmp_path / "out").exists()


def test_json_input_does_not_need_pyyaml(monkeypatch, tmp_path):
    fixture = sorted(FIXTURES.glob("single_trade_clean_loss.json"))[0]
    monkeypatch.setitem(sys.modules, "yaml", None)
    rc = rpc.main(["--input", str(fixture), "--output-dir", str(tmp_path / "out")])
    assert rc == 0
