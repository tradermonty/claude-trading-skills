"""Unit tests for the engine adapter that do not require manifoldbt."""

from types import SimpleNamespace

import pandas as pd
import pytest
from run_backtest import build_strategy, load_bars


def _bars(**overrides):
    values = {
        "timestamp": ["2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z"],
        "open": [101.0, 100.0],
        "high": [102.0, 101.0],
        "low": [100.0, 99.0],
        "close": [101.5, 100.5],
        "volume": [20.0, 10.0],
    }
    values.update(overrides)
    return pd.DataFrame(values)


def test_load_bars_sorts_csv_by_timestamp(tmp_path):
    path = tmp_path / "bars.csv"
    _bars().to_csv(path, index=False)

    loaded = load_bars(str(path))

    assert loaded["timestamp"].is_monotonic_increasing
    assert list(loaded["volume"]) == [10.0, 20.0]


def test_load_bars_rejects_a_missing_file(tmp_path):
    with pytest.raises(SystemExit, match="data file not found"):
        load_bars(str(tmp_path / "missing.csv"))


def test_load_bars_names_missing_columns(tmp_path):
    path = tmp_path / "bars.csv"
    _bars().drop(columns=["volume", "low"]).to_csv(path, index=False)

    with pytest.raises(SystemExit, match="low, volume"):
        load_bars(str(path))


def test_load_bars_rejects_duplicate_timestamps(tmp_path):
    path = tmp_path / "bars.csv"
    _bars(timestamp=["2026-01-01T00:00:00Z"] * 2).to_csv(path, index=False)

    with pytest.raises(SystemExit, match="duplicate timestamps"):
        load_bars(str(path))


class _Expression:
    def __init__(self, value):
        self.value = value

    def _compare(self, operator, other):
        return (operator, self.value, other.value)

    def __gt__(self, other):
        return self._compare(">", other)

    def __lt__(self, other):
        return self._compare("<", other)

    def __ge__(self, other):
        return self._compare(">=", other)

    def __le__(self, other):
        return self._compare("<=", other)


class _Strategy:
    def __init__(self, name):
        self.calls = [("create", name)]

    def signal(self, name, expression):
        self.calls.append(("signal", name, expression))
        return self

    def size(self, expression):
        self.calls.append(("size", expression))
        return self

    def stop_loss(self, *, pct):
        self.calls.append(("stop_loss", pct))
        return self

    def take_profit(self, *, pct):
        self.calls.append(("take_profit", pct))
        return self


class _StrategyFactory:
    @staticmethod
    def create(name):
        return _Strategy(name)


def test_build_strategy_maps_indicators_condition_and_brackets():
    bt = SimpleNamespace(Strategy=_StrategyFactory)
    expr = SimpleNamespace(
        col=lambda value: _Expression(("col", value)),
        lit=lambda value: _Expression(("lit", value)),
        when=lambda condition, yes, no: ("when", condition, yes.value, no.value),
    )
    indicators = SimpleNamespace(
        close="close",
        open="open",
        high="high",
        low="low",
        sma=lambda source, period: ("sma", source, period),
        ema=lambda source, period: ("ema", source, period),
        rsi=lambda source, period: ("rsi", source, period),
    )
    cfg = {
        "name": "adapter_contract",
        "indicators": {
            "fast": {"type": "sma", "source": "close", "period": 5},
            "slow": {"type": "ema", "source": "open", "period": 10},
            "momentum": {"type": "rsi", "source": "high", "period": 14},
        },
        "entry": {"left": "momentum", "op": ">", "right": 30},
        "size": 0.5,
        "stop_loss_pct": 2.0,
        "take_profit_pct": 4.0,
    }

    strategy = build_strategy(cfg, bt, expr, indicators)

    assert strategy.calls[:4] == [
        ("create", "adapter_contract"),
        ("signal", "fast", ("sma", "close", 5)),
        ("signal", "slow", ("ema", "open", 10)),
        ("signal", "momentum", ("rsi", "high", 14)),
    ]
    assert strategy.calls[4][0] == "size"
    assert strategy.calls[-2:] == [("stop_loss", 2.0), ("take_profit", 4.0)]


def test_main_missing_manifoldbt_exits_2_with_stderr_hint(tmp_path, monkeypatch, capsys):
    import json
    import sys

    import run_backtest

    spec = {
        "name": "sma_cross",
        "indicators": {
            "fast": {"type": "sma", "period": 20},
            "slow": {"type": "sma", "period": 60},
        },
        "entry": {"left": "fast", "op": ">", "right": "slow"},
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    monkeypatch.setitem(sys.modules, "manifoldbt", None)  # makes `import manifoldbt` fail
    monkeypatch.setattr(
        sys, "argv", ["run_backtest.py", "--spec", str(spec_path), "--data", "unused.csv"]
    )

    with pytest.raises(SystemExit) as excinfo:
        run_backtest.main()

    captured = capsys.readouterr()
    assert excinfo.value.code == 2
    assert captured.out == ""
    assert "manifoldbt library not found" in captured.err
    assert "pip install -r" in captured.err
    assert "requirements.txt" in captured.err
