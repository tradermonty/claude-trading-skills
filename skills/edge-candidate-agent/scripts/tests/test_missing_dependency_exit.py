"""Missing pandas/numpy exits 2 with a requirements.txt hint (#497)."""

import sys

import auto_detect_candidates as adc


def test_main_without_pandas_exits_2(monkeypatch, capsys, tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    ohlcv.write_bytes(b"")  # exists; never read because pandas import fails first
    monkeypatch.setitem(sys.modules, "pandas", None)  # `import pandas` raises ImportError
    monkeypatch.setattr(
        "sys.argv",
        ["auto_detect_candidates.py", "--ohlcv", str(ohlcv), "--output-dir", str(tmp_path / "o")],
    )
    rc = adc.main()
    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "pandas/numpy libraries not found" in captured.err
    assert "pip install -r" in captured.err
    assert "requirements.txt" in captured.err


def test_missing_dependency_error_is_an_auto_detect_error():
    assert issubclass(adc.MissingDependencyError, adc.AutoDetectError)
