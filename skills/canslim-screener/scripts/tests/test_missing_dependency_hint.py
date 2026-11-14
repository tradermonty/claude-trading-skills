"""Finviz fallback is optional: missing libs degrade with a requirements.txt hint (#497)."""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_finviz_client_import_error_names_requirements(monkeypatch):
    monkeypatch.setitem(sys.modules, "bs4", None)  # `from bs4 import ...` raises ImportError
    with pytest.raises(ImportError) as excinfo:
        _load("finviz_client_missing_dep", SCRIPTS / "finviz_stock_client.py")
    message = str(excinfo.value)
    assert "pip install -r" in message
    assert "requirements.txt" in message


def test_institutional_calculator_degrades_with_stderr_hint(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "bs4", None)
    monkeypatch.delitem(sys.modules, "finviz_stock_client", raising=False)
    mod = _load(
        "institutional_calc_missing_dep", SCRIPTS / "calculators" / "institutional_calculator.py"
    )
    captured = capsys.readouterr()
    assert mod.FINVIZ_AVAILABLE is False
    assert captured.out == ""
    assert "requirements.txt" in captured.err
