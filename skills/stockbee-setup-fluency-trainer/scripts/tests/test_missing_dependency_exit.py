"""Missing ``requests`` on the live FMP update path exits 2 with a hint (#497)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_model_book as bmb  # noqa: E402


def _book(tmp_path):
    book = tmp_path / "book.jsonl"
    rec = {
        "symbol": "TEST",
        "setup": "momentum_burst",
        "date": "2026-01-02",
        "entry": 10.0,
        "stop": 9.0,
    }
    book.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    return book


def test_update_via_fmp_without_requests_exits_2(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(bmb, "requests", None)
    monkeypatch.setattr(bmb, "load_model_book", lambda _p: [{"symbol": "TEST"}])
    monkeypatch.setattr(bmb, "requested_symbols", lambda _r: ["TEST"])
    rc = bmb.main(["update", "--model-book", str(_book(tmp_path))])
    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "ERROR: requests library not found" in captured.err
    assert "requirements.txt" in captured.err
