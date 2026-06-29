import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "run_20pct_study.py"
spec = importlib.util.spec_from_file_location("run_20pct_study", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def make_bars(closes):
    bars = []
    for i, close in enumerate(closes, start=1):
        bars.append(
            mod.Bar(
                date=f"2026-01-{i:02d}",
                open=close * 0.98,
                high=close * 1.05,
                low=close * 0.95,
                close=close,
                volume=1_000_000 + i * 100_000,
            )
        )
    return bars


def test_detects_up_and_down_twenty_pct_events():
    prices = {
        "UPCO": make_bars([10, 10.2, 10.1, 10.4, 10.3, 12.7]),
        "DNCO": make_bars([20, 20.1, 19.8, 20.2, 20.0, 15.5]),
        "FLAT": make_bars([30, 30.2, 29.8, 30.1, 30.0, 30.5]),
    }

    events, metadata = mod.detect_twenty_pct_events(
        prices=prices,
        as_of="2026-01-06",
        lookback_days=5,
        min_abs_return_pct=20,
        min_price=1,
        min_dollar_volume=0,
        include_down_movers=True,
    )

    symbols = {event["symbol"]: event for event in events}
    assert set(symbols) == {"UPCO", "DNCO"}
    assert symbols["UPCO"]["direction"] == "UP"
    assert symbols["DNCO"]["direction"] == "DOWN"
    assert metadata["events_detected"] == 2
    assert symbols["UPCO"]["price_snapshot"]["return_pct"] >= 20
    assert symbols["DNCO"]["price_snapshot"]["return_pct"] <= -20
    assert set(symbols["UPCO"]["outcomes"]) == {"1d", "3d", "5d", "10d", "20d"}


def test_exact_threshold_and_down_mover_gate():
    prices = {
        "UP20": make_bars([10, 10.1, 10.2, 10.1, 10.0, 12.0]),
        "DN20": make_bars([10, 9.9, 10.1, 10.0, 9.8, 8.0]),
    }

    up_only, up_only_meta = mod.detect_twenty_pct_events(
        prices=prices,
        as_of="2026-01-06",
        lookback_days=5,
        min_abs_return_pct=20,
        min_price=1,
        min_dollar_volume=0,
        include_down_movers=False,
    )
    both, both_meta = mod.detect_twenty_pct_events(
        prices=prices,
        as_of="2026-01-06",
        lookback_days=5,
        min_abs_return_pct=20,
        min_price=1,
        min_dollar_volume=0,
        include_down_movers=True,
    )

    assert [event["symbol"] for event in up_only] == ["UP20"]
    assert up_only_meta["skipped"]["threshold_not_met"] == 1
    assert {event["symbol"] for event in both} == {"UP20", "DN20"}
    assert both_meta["events_detected"] == 2


def test_episode_id_reuses_recent_same_symbol_direction():
    prices = {"UPCO": make_bars([10, 10.2, 10.1, 10.4, 10.3, 12.7, 12.8, 13.0])}
    existing = [
        {
            "record_id": "UPCO:2026-01-06:UP:5D",
            "episode_id": "UPCO:2026-01-06:UP",
            "symbol": "UPCO",
            "direction": "UP",
            "event_date": "2026-01-06",
        }
    ]

    events, _ = mod.detect_twenty_pct_events(
        prices=prices,
        as_of="2026-01-08",
        lookback_days=5,
        min_abs_return_pct=20,
        min_price=1,
        min_dollar_volume=0,
        include_down_movers=False,
        existing_records=existing,
        episode_gap_days=5,
    )

    assert len(events) == 1
    assert events[0]["episode_id"] == "UPCO:2026-01-06:UP"
    assert events[0]["event_day_index"] == 2


def test_upsert_records_preserves_review_fields_and_updates_outcomes():
    existing = [
        {
            "record_id": "UPCO:2026-01-06:UP:5D",
            "symbol": "UPCO",
            "human_review": {"reviewed": True, "notes": "keep"},
            "outcomes": {"1d": None},
        }
    ]
    new = [
        {
            "record_id": "UPCO:2026-01-06:UP:5D",
            "symbol": "UPCO",
            "outcomes": {"1d": {"status": "MATURED"}},
        }
    ]

    merged = mod.upsert_records(existing, new)

    assert len(merged) == 1
    assert merged[0]["human_review"] == {"reviewed": True, "notes": "keep"}
    assert merged[0]["outcomes"]["1d"]["status"] == "MATURED"


def test_pick_news_for_event_ignores_future_news():
    news = [
        {"date": "2026-01-11", "title": "Future earnings result"},
        {"date": "2026-01-08", "title": "Prior contract award"},
    ]

    picked = mod.pick_news_for_event(news, "2026-01-10", max_lag_days=3)

    assert picked["title"] == "Prior contract award"
    assert mod.pick_news_for_event([news[0]], "2026-01-10", max_lag_days=3) is None
