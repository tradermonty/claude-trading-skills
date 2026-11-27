"""Build real-shape ftd-detector JSON fixtures from synthetic bars.

The fixtures are produced by ftd-detector's own functions (``get_market_state``,
``assess_post_ftd_health`` and the ``_serialize_index`` JSON writer helper), never
hand-written, so a key rename in ftd-detector shows up as a fixture drift failure.
All bars are synthetic; no market data is used.

Run ``python3 build_ftd_fixtures.py`` to (re)write ``fixtures/ftd_real_shape/*.json``,
or ``python3 build_ftd_fixtures.py --stdout`` to print them as one JSON object.
"""

from __future__ import annotations

import copy
import json
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
FTD_SCRIPTS = HERE.parents[2] / "ftd-detector" / "scripts"
OUT_DIR = HERE / "fixtures" / "ftd_real_shape"

VOL = 1_000_000


def _bar(close, low=None, high=None, vol=VOL):
    bar = {
        "open": close,
        "high": close * 1.004 if high is None else high,
        "low": close * 0.997 if low is None else low,
        "close": close,
        "volume": vol,
    }
    assert bar["low"] <= min(bar["open"], bar["close"]) <= max(bar["open"], bar["close"])
    assert max(bar["open"], bar["close"]) <= bar["high"]
    return bar


def _prefix():
    """Flat lead-in, peak 106, decline to a closing low of 98.9."""
    bars = [_bar(105.0) for _ in range(8)] + [_bar(106.0)]
    bars += [_bar(104.0), _bar(102.5), _bar(101.0), _bar(99.5)]
    bars.append(_bar(98.9, low=98.0, high=100.0))
    return bars


def _attempt(n_days):
    out, price = [], 100.5
    for _ in range(n_days):
        out.append(_bar(price))
        price *= 1.002
    return out


def _advance(start_close, n, step=0.001, vol=VOL):
    out, price = [], start_close
    for _ in range(n):
        price *= 1 + step
        out.append(_bar(price, vol=vol))
    return out


def _decline(start_close, n, step=0.005):
    out, price = [], start_close
    for k in range(n):
        price *= 1 - step
        out.append(_bar(price, vol=1_100_000 + 100_000 * k))
    return out


def _ftd_history(post=()):
    bars = _prefix() + _attempt(3)
    bars.append(_bar(bars[-1]["close"] * 1.015, vol=1_500_000))
    return bars + list(post)


def _dated(bars):
    session = date(2026, 3, 2)
    for bar in bars:
        bar["date"] = session.isoformat()
        session += timedelta(days=1)
        while session.weekday() >= 5:
            session += timedelta(days=1)
    return bars


def _scenarios():
    base = _ftd_history()
    rise = []
    price = 98.9
    for _ in range(12):
        price *= 1.007
        rise.append(_bar(price))
    lead = [_bar(105.0 + 0.05 * (k % 2)) for k in range(62)]
    first_high = next(i for i, b in enumerate(rise) if b["close"] > 106.0)
    peak_run = _advance(base[-1]["close"], 20, step=0.004)
    return {
        "correction_rally_attempt_day3": _prefix() + _attempt(3),
        "correction_rally_failed": _prefix() + _advance(98.9, 11, step=0.003),
        "ftd_confirmed_fresh": base,
        "ftd_confirmed_age_6": _ftd_history(_advance(base[-1]["close"], 6)),
        "ftd_confirmed_age_16": _ftd_history(_advance(base[-1]["close"], 16)),
        "uptrend_resumed": lead + _prefix()[8:] + rise[: first_high + 1],
        "uptrend_under_pressure": base + peak_run + _decline(peak_run[-1]["close"], 5),
    }


def build() -> dict[str, dict]:
    sys.path.insert(0, str(FTD_SCRIPTS))
    from ftd_detector import _serialize_index
    from post_ftd_monitor import assess_post_ftd_health
    from rally_tracker import get_market_state

    out = {}
    for name, bars in _scenarios().items():
        chrono = _dated(copy.deepcopy(bars))
        # Both indices see the same synthetic bars; most recent first for get_market_state.
        state = get_market_state(list(reversed(chrono)), list(reversed(chrono)))
        state = assess_post_ftd_health(state, chrono, chrono)
        out[name] = {
            "metadata": {"schema_version": 2},
            "market_state": {
                "combined_state": state["combined_state"],
                "market_status": state.get("market_status"),
                "dual_confirmation": state["dual_confirmation"],
                "ftd_index": state.get("ftd_index"),
                "data_gap": bool(state.get("data_gap")),
            },
            "data_gap": bool(state.get("data_gap")),
            "sp500": _serialize_index(state["sp500"]),
            "nasdaq": _serialize_index(state["nasdaq"]),
            "quality_score": state.get("quality_score", {}),
            "post_ftd_distribution": state.get("post_ftd_distribution", {}),
            "ftd_invalidation": state.get("ftd_invalidation", {}),
            "power_trend": state.get("power_trend", {}),
        }
    return out


def _normalized(payload: dict) -> dict:
    return json.loads(json.dumps(payload, default=str))


if __name__ == "__main__":
    fixtures = {k: _normalized(v) for k, v in build().items()}
    if "--stdout" in sys.argv:
        print(json.dumps(fixtures, sort_keys=True))
    else:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        for name, payload in fixtures.items():
            (OUT_DIR / f"{name}.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            ms = payload["market_state"]
            print(
                name,
                ms["combined_state"],
                ms["market_status"],
                payload["ftd_invalidation"].get("days_since_ftd"),
            )
