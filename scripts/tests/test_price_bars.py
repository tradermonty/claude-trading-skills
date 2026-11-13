"""Tests for the canonical price-bar helper (issue #655)."""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load():
    path = REPO_ROOT / "scripts" / "price_bars" / "price_bars.py"
    spec = importlib.util.spec_from_file_location("canonical_price_bars", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["canonical_price_bars"] = module
    spec.loader.exec_module(module)
    return module


pb = _load()


@pytest.mark.parametrize(
    "bar",
    [
        {},
        {"close": None},
        {"close": True},
        {"close": False},
        {"close": "101.5"},
        {"close": math.nan},
        {"close": math.inf},
        {"close": -math.inf},
        {"close": 0},
        {"close": 0.0},
        {"close": -1.5},
        {"close": [1]},
    ],
)
def test_read_price_rejects_missing_and_invalid_values(bar):
    assert pb.read_price(bar, "close") is None


@pytest.mark.parametrize("value", [101, 101.5, 1e-9])
def test_read_price_returns_original_positive_value(value):
    result = pb.read_price({"close": value}, "close")
    assert result == value
    assert type(result) is type(value)


def test_read_price_allow_zero_accepts_zero_only():
    assert pb.read_price({"volume": 0}, "volume", allow_zero=True) == 0
    assert pb.read_price({"volume": 0.0}, "volume", allow_zero=True) == 0.0
    assert pb.read_price({"volume": -1}, "volume", allow_zero=True) is None
    assert pb.read_price({"volume": math.nan}, "volume", allow_zero=True) is None
    assert pb.read_price({"volume": 0}, "volume") is None


def test_read_price_rejects_non_mapping_bar():
    assert pb.read_price(None, "close") is None
    assert pb.read_price([("close", 1.0)], "close") is None


def test_read_price_accepts_numpy_scalars_when_available():
    np = pytest.importorskip("numpy")
    assert pb.read_price({"close": np.float64(2.5)}, "close") == 2.5
    assert pb.read_price({"close": np.int64(3)}, "close") == 3
    assert pb.read_price({"close": np.float64("nan")}, "close") is None
    assert pb.read_price({"close": np.bool_(True)}, "close") is None


def _bars():
    return [
        {"date": "d0", "close": 10.0, "volume": 100},
        {"date": "d1", "close": None, "volume": 100},
        {"date": "d2", "close": 11.0, "volume": 0},
        {"date": "d3", "close": 12.0},
        {"date": "d4", "close": 13.0, "volume": 100},
    ]


def test_find_bar_gaps_chronological():
    report = pb.find_bar_gaps(
        _bars(), ("close", "volume"), zero_ok=("volume",), order="chronological"
    )
    assert report == {
        "checked_bars": 5,
        "bad_bars": 2,
        "bad_indices": [1, 3],
        "bad_dates": ["d1", "d3"],
        "latest_bad": "d3",
        "required": ["close", "volume"],
    }


def test_find_bar_gaps_newest_first_latest_is_first_bad():
    bars = list(reversed(_bars()))
    report = pb.find_bar_gaps(bars, ("close", "volume"), zero_ok=("volume",), order="newest_first")
    assert report["bad_indices"] == [1, 3]
    assert report["bad_dates"] == ["d3", "d1"]
    assert report["latest_bad"] == "d3"


def test_find_bar_gaps_zero_volume_is_bad_without_zero_ok():
    report = pb.find_bar_gaps(_bars(), ("volume",), order="chronological")
    assert report["bad_indices"] == [2, 3]


def test_find_bar_gaps_clean_and_empty():
    clean = pb.find_bar_gaps([{"close": 1.0}], ("close",), order="chronological")
    assert clean["bad_bars"] == 0 and clean["latest_bad"] is None and clean["bad_dates"] == []
    empty = pb.find_bar_gaps([], ("close",), order="newest_first")
    assert empty["checked_bars"] == 0 and empty["bad_bars"] == 0


def test_find_bar_gaps_caps_bad_dates_at_ten_most_recent():
    bars = [{"date": f"d{i:02d}"} for i in range(15)]
    report = pb.find_bar_gaps(bars, ("close",), order="chronological")
    assert report["bad_bars"] == 15
    assert report["bad_dates"] == [f"d{i:02d}" for i in range(5, 15)]
    assert report["latest_bad"] == "d14"


def test_find_bar_gaps_non_mapping_bar_and_missing_date():
    report = pb.find_bar_gaps([None, {"close": 1.0}], ("close",), order="chronological")
    assert report["bad_indices"] == [0]
    assert report["latest_bad"] == "index 0"


def test_find_bar_gaps_requires_valid_order():
    with pytest.raises(ValueError, match="order"):
        pb.find_bar_gaps([], ("close",), order="oldest")
    with pytest.raises(TypeError):
        pb.find_bar_gaps([], ("close",))  # order is a required keyword
