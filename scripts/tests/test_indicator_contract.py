"""Cross-skill contract test for the copy-pasted RSI and EMA indicators (issue #663).

Skills are packaged standalone, so each keeps its own copy of the indicator.
This test feeds identical fixtures to every copy and asserts identical results,
so a copy cannot drift without failing CI.

RSI contract (all copies, prices oldest first, Wilder smoothing):
  * result rounded to 2 decimals, or ``None`` when not evaluable
  * ``None`` for: fewer than ``period + 1`` prices, any NaN/inf/non-positive
    price, invalid period, non-finite result, and a flat series (no movement is
    undefined, not overbought)

EMA contract (all scalar copies):
  * each copy documents its price order; the adapters below normalise to
    oldest first
  * fewer than ``period`` prices returns the simple average of the prices given
  * empty prices or ``period < 1`` raises ``ValueError``
"""

from __future__ import annotations

import importlib.util
import math
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SKILLS = REPO_ROOT / "skills"

# Sibling module names that several skills define with different content.
_SIBLING_NAMES = (
    "fmp_client",
    "math_utils",
    "_price_bars",
    "_market_calendar",
    "dividend_history",
    "fmp_adapter",
    "ftd_lifecycle",
    "_fmp_compat",
)


def _load(rel_path: str, tag: str):
    """Load a skill file by path in isolation, restoring sys.modules afterwards."""
    abs_path = REPO_ROOT / rel_path
    saved_modules = {n: sys.modules.pop(n) for n in _SIBLING_NAMES if n in sys.modules}
    saved_path = list(sys.path)
    sys.path.insert(0, str(abs_path.parent))
    if abs_path.parent.name == "calculators":
        sys.path.insert(0, str(abs_path.parent.parent))
    name = f"_indicator_contract_{tag}"
    try:
        spec = importlib.util.spec_from_file_location(name, str(abs_path))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for n in _SIBLING_NAMES:
            sys.modules.pop(n, None)
        sys.modules.update(saved_modules)
        sys.path[:] = saved_path


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------


def _rsi_adapters():
    pd = pytest.importorskip("pandas")
    dg = _load(
        "skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py",
        "rsi_dg",
    )
    vd = _load("skills/value-dividend-screener/scripts/screen_dividend_stocks.py", "rsi_vd")
    th = _load("skills/theme-detector/scripts/etf_scanner.py", "rsi_th")
    return {
        "dividend-growth": lambda p, period=14: dg.RSICalculator.calculate_rsi(list(p), period),
        "value-dividend": lambda p, period=14: vd.RSICalculator.calculate_rsi(list(p), period),
        "theme-detector": lambda p, period=14: th.ETFScanner._calculate_rsi(
            pd.Series(list(p), dtype=object if any(isinstance(x, str) for x in p) else float),
            period,
        ),
    }


@pytest.fixture(scope="module")
def rsi_copies():
    return _rsi_adapters()


_MIXED = [
    44.0, 44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84,
    46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22,
]  # fmt: skip
_NAN = float("nan")
_INF = float("inf")

# (id, prices, period, expected). ``expected`` is a float or None.
RSI_CASES = [
    ("rising", [float(i) for i in range(1, 30)], 14, 100.0),
    ("falling", [float(i) for i in range(30, 1, -1)], 14, 0.0),
    ("period-3-known", [10.0, 11.0, 10.0, 11.0, 13.0], 3, 83.33),
    ("flat", [100.0] * 30, 14, None),
    ("flat-exact-minimum", [100.0] * 15, 14, None),
    ("short", [100.0 + i for i in range(14)], 14, None),
    ("empty", [], 14, None),
    ("one-nan", [float(i) for i in range(1, 31)][:15] + [_NAN] + [20.0] * 10, 14, None),
    ("nan-at-edge", [_NAN] + [float(i) for i in range(1, 30)], 14, None),
    ("inf", [100.0] * 14 + [_INF], 14, None),
    ("zero-filled", [0.0] * 30, 14, None),
    ("zero-in-series", [float(i) for i in range(1, 30)][:10] + [0.0] + [20.0] * 10, 14, None),
    ("negative", [-1.0 * i for i in range(1, 30)], 14, None),
    ("overflow", [1e308, 1.0] * 15, 14, None),
    ("period-zero", [100.0 + i for i in range(30)], 0, None),
    ("period-negative", [100.0 + i for i in range(30)], -1, None),
]


@pytest.mark.parametrize("case", RSI_CASES, ids=[c[0] for c in RSI_CASES])
def test_rsi_copies_agree(rsi_copies, case):
    _, prices, period, expected = case
    results = {name: fn(prices, period) for name, fn in rsi_copies.items()}
    assert results == {name: expected for name in rsi_copies}, results


def test_rsi_copies_agree_on_mixed_series(rsi_copies):
    results = {name: fn(_MIXED, 14) for name, fn in rsi_copies.items()}
    assert len(set(results.values())) == 1, results
    value = next(iter(results.values()))
    assert value is not None and 0 < value < 100
    assert value == round(value, 2)


# ---------------------------------------------------------------------------
# EMA
# ---------------------------------------------------------------------------


def _ema_adapters():
    """name -> fn(prices_oldest_first, period) using each copy's documented order."""
    mt_math = _load("skills/market-top-detector/scripts/calculators/math_utils.py", "ema_mtm")
    ibd_math = _load("skills/ibd-distribution-day-monitor/scripts/math_utils.py", "ema_ibd")
    canslim_calc = _load(
        "skills/canslim-screener/scripts/calculators/market_calculator.py", "ema_cs_calc"
    )
    post_ftd = _load("skills/ftd-detector/scripts/post_ftd_monitor.py", "ema_post_ftd")
    para = _load("skills/parabolic-short-trade-planner/scripts/math_helpers.py", "ema_para")
    mt_client = _load("skills/market-top-detector/scripts/fmp_client.py", "ema_mt_client")
    cs_client = _load("skills/canslim-screener/scripts/fmp_client.py", "ema_cs_client")
    ftd_client = _load("skills/ftd-detector/scripts/fmp_client.py", "ema_ftd_client")

    def newest_first(fn):
        return lambda prices, period: fn(list(reversed(prices)), period)

    def client_method(cls, scripts_dir=None):
        # The method does not use ``self``; avoid constructing a client.
        def call(prices, period):
            if scripts_dir is None:
                return cls.calculate_ema(None, prices, period)
            # market-top's wrapper lazily imports its sibling ``calculators`` package.
            names = [n for n in sys.modules if n.split(".")[0] == "calculators"]
            saved = {n: sys.modules.pop(n) for n in names}
            sys.path.insert(0, str(scripts_dir))
            try:
                return cls.calculate_ema(None, prices, period)
            finally:
                sys.path.remove(str(scripts_dir))
                for n in [n for n in sys.modules if n.split(".")[0] == "calculators"]:
                    del sys.modules[n]
                sys.modules.update(saved)

        return newest_first(call)

    return {
        "market-top math_utils (newest first)": newest_first(mt_math.calc_ema),
        "ibd-distribution-day math_utils (newest first)": newest_first(ibd_math.calc_ema),
        "canslim market_calculator (newest first)": newest_first(canslim_calc.calculate_ema),
        "market-top fmp_client (newest first)": client_method(
            mt_client.FMPClient, SKILLS / "market-top-detector" / "scripts"
        ),
        "canslim fmp_client (newest first)": client_method(cs_client.FMPClient),
        "ftd fmp_client (newest first)": client_method(ftd_client.FMPClient),
        "ftd post_ftd_monitor (oldest first)": post_ftd._calculate_ema,
        "parabolic math_helpers (oldest first)": para.ema,
    }


@pytest.fixture(scope="module")
def ema_copies():
    return _ema_adapters()


def _series(n):
    return [100.0 + (i % 7) * 1.5 - (i % 3) * 0.8 + i * 0.1 for i in range(n)]


def _reference_ema(prices_oldest_first, period):
    if len(prices_oldest_first) < period:
        return sum(prices_oldest_first) / len(prices_oldest_first)
    k = 2 / (period + 1)
    ema = sum(prices_oldest_first[:period]) / period
    for p in prices_oldest_first[period:]:
        ema = p * k + ema * (1 - k)
    return ema


EMA_VALUE_CASES = [
    ("normal", _series(80), 21),
    ("exact-period", _series(21), 21),
    ("short-history-falls-back-to-average", _series(5), 21),
    ("single-price", [123.0], 21),
    ("flat", [50.0] * 60, 21),
    ("period-one", _series(10), 1),
]


@pytest.mark.parametrize("case", EMA_VALUE_CASES, ids=[c[0] for c in EMA_VALUE_CASES])
def test_ema_copies_agree(ema_copies, case):
    _, prices, period = case
    expected = _reference_ema(prices, period)
    for name, fn in ema_copies.items():
        assert fn(prices, period) == pytest.approx(expected, rel=1e-12), name


def test_ema_copies_propagate_nan_identically(ema_copies):
    prices = _series(40)
    prices[10] = _NAN
    for name, fn in ema_copies.items():
        assert math.isnan(fn(prices, 21)), name


@pytest.mark.parametrize("period", [0, -1])
def test_ema_copies_reject_invalid_period(ema_copies, period):
    for name, fn in ema_copies.items():
        with pytest.raises(ValueError):
            fn(_series(30), period)
        assert name


def test_ema_copies_reject_empty_prices(ema_copies):
    for name, fn in ema_copies.items():
        with pytest.raises(ValueError):
            fn([], 21)
        assert name


def test_uptrend_series_ema_contract():
    """Series variant: not numerically comparable, but shares order and empty handling."""
    mod = _load("skills/uptrend-analyzer/scripts/calculators/momentum_calculator.py", "ema_up")
    assert mod._ema([]) == []
    assert mod._ema([7.0]) == [7.0]
    assert mod._ema([5.0] * 6) == [5.0] * 6
    rising = mod._ema([1.0, 2.0, 3.0, 4.0], span=3)
    assert len(rising) == 4
    assert rising == sorted(rising)  # oldest-first input: output follows the trend
    assert rising[-1] < 4.0  # lags the latest value
