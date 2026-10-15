"""DataFrame-level tests for auto_detect_candidates scanners and feature pipeline."""

from datetime import date, timedelta
from pathlib import Path

import auto_detect_candidates as adc
import numpy as np
import pandas as pd
import pytest
import synthetic_ohlcv as so
import yaml

pytest.importorskip("pyarrow")

AS_OF = date(2026, 2, 20)


@pytest.fixture(scope="module")
def market_path(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("mkt") / "market.parquet"
    so.build_market().to_parquet(path)
    return path


@pytest.fixture(scope="module")
def market(market_path):
    full, latest, resolved = adc.compute_features(market_path, None)
    regime, summary, tradable = adc.compute_regime(full, latest, resolved, 5.0, 1_000_000.0)
    return {
        "full": full,
        "latest": latest,
        "date": resolved,
        "regime": regime,
        "summary": summary,
        "tradable": tradable,
    }


# --- compute_features ---------------------------------------------------------


def test_compute_features_resolves_latest_date_and_features(market) -> None:
    assert market["date"] == AS_OF
    assert set(market["latest"]["symbol"]) == {
        "BRK",
        "GAPPER",
        "PANIC",
        "SPY",
        *so.FILLER_SYMBOLS,
    }
    row = market["latest"].set_index("symbol").loc["PANIC"]
    assert row["ret_1d"] == pytest.approx(-0.10, abs=1e-9)
    assert row["rel_volume"] > 2.5
    gap_row = market["latest"].set_index("symbol").loc["GAPPER"]
    assert gap_row["gap"] == pytest.approx(0.065, abs=1e-9)
    assert 0.0 <= gap_row["close_pos"] <= 1.0
    assert not np.isinf(market["full"].select_dtypes("number").to_numpy()).any()


def test_compute_features_lowercases_columns_and_symbols(tmp_path: Path) -> None:
    df = so.build_market(n_days=60)
    df.columns = [c.upper() for c in df.columns]
    df["SYMBOL"] = df["SYMBOL"].str.lower()
    path = tmp_path / "upper.parquet"
    df.to_parquet(path)
    _, latest, resolved = adc.compute_features(path, None)
    assert resolved == AS_OF
    assert "BRK" in set(latest["symbol"])


def test_compute_features_missing_columns(tmp_path: Path) -> None:
    path = tmp_path / "bad.parquet"
    so.build_market(n_days=30).drop(columns=["volume", "open"]).to_parquet(path)
    with pytest.raises(adc.AutoDetectError, match="missing columns: open, volume"):
        adc.compute_features(path, None)


def test_compute_features_no_valid_timestamps(tmp_path: Path) -> None:
    df = so.build_market(n_days=30)
    df["timestamp"] = "not a date"
    path = tmp_path / "nat.parquet"
    df.to_parquet(path)
    with pytest.raises(adc.AutoDetectError, match="no valid timestamps"):
        adc.compute_features(path, None)


def test_compute_features_as_of_before_data(market_path) -> None:
    with pytest.raises(adc.AutoDetectError, match="no OHLCV data at or before as_of=2000-01-03"):
        adc.compute_features(market_path, date(2000, 1, 3))


def test_compute_features_as_of_falls_back_to_prior_trading_day(market_path) -> None:
    saturday = date(2026, 2, 14)
    assert saturday.weekday() == 5
    full, latest, resolved = adc.compute_features(market_path, saturday)
    assert resolved == date(2026, 2, 13)
    assert full["date"].max() == resolved
    assert set(latest["date"]) == {resolved}


# --- compute_regime -----------------------------------------------------------


def test_compute_regime_riskon_summary(market) -> None:
    summary = market["summary"]
    assert market["regime"] == "RiskOn"
    assert summary["regime_label"] == "RiskOn"
    assert summary["as_of"] == "2026-02-20"
    assert summary["universe_count"] == 12
    assert summary["spy_above_ma200"] is True
    assert summary["spy_return_1d"] is not None
    assert summary["risk_on_score"] >= 65
    assert summary["risk_on_score"] > summary["risk_off_score"]
    assert 0.0 <= summary["pct_above_ma50"] <= 1.0
    assert "rs_rank_pct" in market["tradable"].columns
    assert market["tradable"]["rs_rank_pct"].max() == 1.0


def test_compute_regime_riskoff_on_correlated_selloff(tmp_path: Path) -> None:
    path = tmp_path / "selloff.parquet"
    so.build_selloff().to_parquet(path)
    full, latest, resolved = adc.compute_features(path, None)
    label, summary, _ = adc.compute_regime(full, latest, resolved, 5.0, 1_000_000.0)
    assert label == "RiskOff"
    assert summary["spy_above_ma200"] is False
    assert summary["pct_above_ma50"] == 0.0
    assert summary["avg_pair_corr_20"] > 0.9
    assert summary["risk_off_score"] >= 65


def test_compute_regime_without_spy_uses_breadth_and_market_vol(tmp_path: Path) -> None:
    df = so.build_market()
    path = tmp_path / "nospy.parquet"
    df[df["symbol"] != "SPY"].to_parquet(path)
    full, latest, resolved = adc.compute_features(path, None)
    _, summary, _ = adc.compute_regime(full, latest, resolved, 5.0, 1_000_000.0)
    assert summary["spy_return_1d"] is None
    assert summary["spy_above_ma200"] == (summary["pct_above_ma200"] >= 0.5)
    # Volatility falls back to the equal-weight market return series.
    assert summary["rv20"] is not None
    assert summary["rv60"] is not None
    assert summary["vol_trend"] == pytest.approx(summary["rv20"] / summary["rv60"], rel=1e-2)


def test_compute_regime_no_tradable_symbols(market) -> None:
    with pytest.raises(adc.AutoDetectError, match="no tradable symbols remain"):
        adc.compute_regime(market["full"], market["latest"], market["date"], 1e9, 1_000_000.0)
    with pytest.raises(adc.AutoDetectError, match="no tradable symbols remain"):
        adc.compute_regime(market["full"], market["latest"], market["date"], 5.0, 1e12)


# --- detect_anomalies ---------------------------------------------------------


def test_detect_anomalies_on_synthetic_market(market) -> None:
    anomalies = adc.detect_anomalies(market["tradable"], market["summary"], top_k=50)
    metrics = {(a["symbol"], a["metric"]) for a in anomalies}
    assert ("GAPPER", "gap") in metrics
    assert ("PANIC", "ret_1d") in metrics
    assert ("BRK", "rel_volume") in metrics
    assert all(a["abs_z"] >= 2.0 for a in anomalies)
    assert [a["abs_z"] for a in anomalies] == sorted((a["abs_z"] for a in anomalies), reverse=True)
    panic = next(a for a in anomalies if a["symbol"] == "PANIC" and a["metric"] == "ret_1d")
    assert panic["value"] == pytest.approx(-0.1, abs=1e-5)
    assert panic["z"] < 0
    assert len(adc.detect_anomalies(market["tradable"], market["summary"], top_k=2)) == 2
    assert adc.detect_anomalies(market["tradable"], market["summary"], top_k=0) == []


def _z_frame() -> pd.DataFrame:
    nan = float("nan")
    return pd.DataFrame(
        [
            {
                "symbol": "S1",
                "ret_1d": 0.05,
                "rel_volume": 1.0,
                "gap": 0.0,
                "atr_pct": 0.02,
                "ret_1d_z": 3.0,
                "rel_volume_z": nan,
                "gap_z": 0.5,
                "atr_pct_z": 1.0,
            },
            {
                "symbol": "S2",
                "ret_1d": 0.0,
                "rel_volume": 1.0,
                "gap": nan,
                "atr_pct": 0.02,
                "ret_1d_z": 0.0,
                "rel_volume_z": 0.0,
                "gap_z": -2.5,
                "atr_pct_z": -1.9,
            },
        ]
    )


def test_detect_anomalies_skips_nan_and_small_z_and_nulls_nan_value() -> None:
    anomalies = adc.detect_anomalies(_z_frame(), {}, top_k=10)
    assert [(a["symbol"], a["metric"]) for a in anomalies] == [
        ("S1", "ret_1d"),
        ("S2", "gap"),
    ]
    assert anomalies[1]["value"] is None
    assert anomalies[1]["z"] == -2.5
    assert anomalies[0]["comment"] == "ret_1d z-score exceeded 2.0"


def test_detect_anomalies_adds_market_level_signals() -> None:
    summary = {
        "avg_pair_corr_20": 0.70,
        "vol_trend": 1.2,
        "pct_above_ma50": 0.30,
        "spy_return_1d": 0.01,
    }
    anomalies = adc.detect_anomalies(_z_frame(), summary, top_k=10)
    assert [a["metric"] for a in anomalies[:2]] == ["breadth_divergence", "riskoff_combo"]
    assert anomalies[0]["abs_z"] == 95.0
    assert anomalies[0]["value"] == 0.3
    assert anomalies[1]["abs_z"] == 99.0
    assert anomalies[1]["value"] == 1.2
    assert all(a["scope"] == "market" for a in anomalies[:2])
    assert len(adc.detect_anomalies(_z_frame(), summary, top_k=1)) == 1

    calm = {"avg_pair_corr_20": 0.3, "vol_trend": 0.9, "pct_above_ma50": 0.6, "spy_return_1d": 0.0}
    assert all(a["scope"] == "stock" for a in adc.detect_anomalies(_z_frame(), calm, 10))


# --- scan_candidates / reversal -------------------------------------------------


def test_scan_candidates_finds_breakout_and_gap(market) -> None:
    hints = adc.normalize_hints(
        [{"title": "AI leaders", "preferred_entry_family": "pivot_breakout", "symbols": ["BRK"]}]
    )
    watchlist, seeds = adc.scan_candidates(market["tradable"], market["regime"], hints, top_n=2)
    by_key = {(w["symbol"], w["entry_family"]): w for w in watchlist}
    assert ("BRK", "pivot_breakout") in by_key
    assert ("GAPPER", "gap_up_continuation") in by_key
    assert ("PANIC", "pivot_breakout") not in by_key
    scores = [w["priority_score"] for w in watchlist]
    assert scores == sorted(scores, reverse=True)
    assert seeds == watchlist[:2]

    brk = by_key[("BRK", "pivot_breakout")]
    assert brk["matched_hints"] == ["AI leaders"]
    assert brk["hypothesis_type"] == "breakout"
    assert brk["mechanism_tag"] == "behavior"
    assert "close > high20_prev" in brk["conditions"]
    gap = by_key[("GAPPER", "gap_up_continuation")]
    assert gap["hypothesis_type"] == "earnings_drift"
    assert gap["mechanism_tag"] == "structure"
    assert gap["matched_hints"] == []
    assert gap["gap"] == pytest.approx(0.065, abs=1e-9)


def test_scan_candidates_hint_boost_raises_score(market) -> None:
    base, _ = adc.scan_candidates(market["tradable"], market["regime"], [], top_n=5)
    hints = adc.normalize_hints(
        [{"title": "t", "preferred_entry_family": "pivot_breakout", "symbols": ["BRK"]}]
    )
    boosted, _ = adc.scan_candidates(market["tradable"], market["regime"], hints, top_n=5)
    score = {(w["symbol"], w["entry_family"]): w["priority_score"] for w in base}
    score_b = {(w["symbol"], w["entry_family"]): w["priority_score"] for w in boosted}
    assert score_b[("BRK", "pivot_breakout")] >= score[("BRK", "pivot_breakout")]
    assert score_b[("GAPPER", "gap_up_continuation")] == score[("GAPPER", "gap_up_continuation")]


def test_scan_candidates_empty_and_negative_top_n(market) -> None:
    empty = market["tradable"].iloc[0:0]
    assert adc.scan_candidates(empty, "Neutral", [], top_n=5) == ([], [])
    watchlist, seeds = adc.scan_candidates(market["tradable"], "Neutral", [], top_n=-1)
    assert watchlist and seeds == []


def test_scan_reversal_candidates_detects_panic(market) -> None:
    hints = adc.normalize_hints(
        [
            {
                "title": "Panic washout",
                "preferred_entry_family": "panic_reversal",
                "symbols": ["PANIC"],
            }
        ]
    )
    found = adc.scan_reversal_candidates(market["tradable"], market["regime"], hints)
    assert [c["symbol"] for c in found] == ["PANIC"]
    cand = found[0]
    assert cand["entry_family"] == "panic_reversal"
    assert cand["holding_horizon"] == "5D"
    assert cand["matched_hints"] == ["Panic washout"]
    assert cand["ret_1d"] == pytest.approx(-0.10, abs=1e-9)
    assert "ret_1d <= -0.07" in cand["conditions"]
    plain = adc.scan_reversal_candidates(market["tradable"], market["regime"], [])
    # hint boost is 12 * 0.6 = 7.2
    assert cand["priority_score"] == pytest.approx(plain[0]["priority_score"] + 7.2, abs=0.011)
    assert adc.scan_reversal_candidates(market["tradable"], "Neutral", [], top_n=0) == []


def test_scan_reversal_candidates_none_when_no_shock(market) -> None:
    calm = market["tradable"][market["tradable"]["symbol"] != "PANIC"]
    assert adc.scan_reversal_candidates(calm, "Neutral", []) == []


# --- regime shift ---------------------------------------------------------------


def _breadth_frame(above_counts: list[int], avg_ret: float, symbols: int = 10) -> pd.DataFrame:
    start = date(2026, 1, 1)
    rows = []
    for i, above in enumerate(above_counts):
        for s in range(symbols):
            rows.append(
                {
                    "date": start + timedelta(days=i),
                    "symbol": f"S{s}",
                    "close": 101.0 if s < above else 99.0,
                    "ma50": 100.0,
                    "ma200": 100.0,
                    "ret_1d": avg_ret,
                }
            )
    return pd.DataFrame(rows)


def test_regime_shift_risk_on_transition() -> None:
    counts = [2] * 6 + [2, 3, 4, 5, 6, 7, 8, 8]
    frame = _breadth_frame(counts, 0.002)
    target = frame["date"].max()
    out = adc.scan_regime_shift_candidate(
        frame, target, {"vol_trend": 1.0, "avg_pair_corr_20": 0.3}
    )
    assert len(out) == 1
    cand = out[0]
    assert cand["symbol"] == "MARKET_BASKET"
    assert cand["hypothesis_type"] == "regime_shift"
    assert cand["entry_family"] is None
    assert cand["trend_filter"] == ["risk_on_transition"]
    assert cand["priority_score"] == 80.0
    assert cand["conditions"][0] == "breadth_delta_7d=0.6"
    assert "vol_trend=1.0" in cand["conditions"]


def test_regime_shift_risk_off_transition() -> None:
    counts = [8] * 6 + [8, 7, 6, 5, 4, 3, 2, 2]
    frame = _breadth_frame(counts, -0.004)
    out = adc.scan_regime_shift_candidate(
        frame, frame["date"].max(), {"vol_trend": 1.3, "avg_pair_corr_20": 0.8}
    )
    assert out[0]["trend_filter"] == ["risk_off_transition"]
    assert out[0]["description"].startswith("Breadth deterioration")
    assert out[0]["conditions"][1] == "ret_5d=-0.02"


def test_regime_shift_returns_empty_when_conditions_not_met() -> None:
    summary = {"vol_trend": 1.0, "avg_pair_corr_20": 0.3}
    flat = _breadth_frame([5] * 14, 0.001)
    assert adc.scan_regime_shift_candidate(flat, flat["date"].max(), summary) == []

    rising = _breadth_frame([2] * 6 + [2, 3, 4, 5, 6, 7, 8, 8], 0.002)
    target = rising["date"].max()
    # Rising breadth but volatility trend too high for a RiskOn transition.
    assert (
        adc.scan_regime_shift_candidate(rising, target, {"vol_trend": 1.5, "avg_pair_corr_20": 0.3})
        == []
    )
    # Missing market summary values.
    assert adc.scan_regime_shift_candidate(rising, target, {"vol_trend": None}) == []
    # Target date missing from the frame.
    assert adc.scan_regime_shift_candidate(rising, date(2030, 1, 1), summary) == []
    # Too little history.
    short = _breadth_frame([2, 3, 4, 5, 6, 7, 8, 8], 0.002)
    assert adc.scan_regime_shift_candidate(short, short["date"].max(), summary) == []
    # No rows with moving averages.
    no_ma = rising.assign(ma50=np.nan)
    assert adc.scan_regime_shift_candidate(no_ma, target, summary) == []


# --- correlation chain ----------------------------------------------------------


def _chain_frames(follower_today: dict[str, float] | None = None, n_days: int = 60):
    rng = np.random.default_rng(3)
    dates = [date(2025, 11, 1) + timedelta(days=i) for i in range(n_days)]
    leader = rng.normal(0.0, 0.02, n_days)
    leader[-2] = 0.01
    leader[-1] = 0.08
    series: dict[str, np.ndarray] = {"LEAD": leader}
    for name in ("F1", "F2", "F3"):
        follow = np.roll(leader, 1) * 0.8 + rng.normal(0, 0.003, n_days)
        follow[0] = 0.0
        series[name] = follow
    for k in range(6):
        series[f"X{k}"] = rng.normal(0.0, 0.01, n_days)
    today_override = {"F1": 0.004, "F2": 0.005, "F3": 0.03, **(follower_today or {})}
    for name, val in today_override.items():
        series[name][-1] = val
    rows = []
    for name, rets in series.items():
        for d, r in zip(dates, rets):
            rows.append({"date": d, "symbol": name, "close": 100.0, "volume": 1e6, "ret_1d": r})
    full = pd.DataFrame(rows)
    tradable = pd.DataFrame(
        [
            {
                "symbol": name,
                "ret_1d": rets[-1],
                "close": 100.0,
                "ma50": 90.0 if name != "F2" else 110.0,
                "rel_volume": 1.5,
            }
            for name, rets in series.items()
        ]
    )
    return full, tradable, dates[-1]


def test_correlation_chain_finds_followers_of_big_mover() -> None:
    full, tradable, target = _chain_frames()
    out = adc.scan_correlation_chain_candidates(full, tradable, target, top_n=5)
    symbols = [c["symbol"] for c in out]
    # F3 already moved today (>= 1.5%), so it is not a follower candidate.
    assert "F3" not in symbols
    assert "F1" in symbols and "F2" in symbols
    assert "LEAD" not in symbols
    assert all(c["hypothesis_type"] == "sector_x_stock" for c in out)
    assert all(c["conditions"][0] == "leader=LEAD" for c in out)
    assert len(symbols) == len(set(symbols))
    scores = {c["symbol"]: c["priority_score"] for c in out}
    # F1 trades above its MA50 (+10) while F2 is below it (+4): same leader, similar corr.
    assert scores["F1"] > scores["F2"]
    assert [c["priority_score"] for c in out] == sorted(
        (c["priority_score"] for c in out), reverse=True
    )
    assert len(adc.scan_correlation_chain_candidates(full, tradable, target, top_n=1)) == 1


def test_correlation_chain_early_exits() -> None:
    full, tradable, target = _chain_frames()
    assert adc.scan_correlation_chain_candidates(full, tradable, date(2031, 1, 1)) == []

    narrow = full[full["symbol"].isin(["LEAD", "F1", "F2"])]
    assert adc.scan_correlation_chain_candidates(narrow, tradable, target) == []

    quiet = tradable.assign(ret_1d=0.001)
    assert adc.scan_correlation_chain_candidates(full, quiet, target) == []

    outsider = tradable.copy()
    outsider.loc[len(outsider)] = ["ZZZ", 0.2, 100.0, 90.0, 1.0]
    outsider.loc[outsider["symbol"] == "LEAD", "ret_1d"] = 0.001
    # The only big mover is not part of the lagged-correlation panel.
    assert adc.scan_correlation_chain_candidates(full, outsider, target) == []


# --- calendar anomaly -----------------------------------------------------------


@pytest.fixture(scope="module")
def seasonal(tmp_path_factory):
    path = tmp_path_factory.mktemp("seas") / "seasonal.parquet"
    so.build_seasonal_history().to_parquet(path)
    full, latest, resolved = adc.compute_features(path, None)
    _, _, tradable = adc.compute_regime(full, latest, resolved, 5.0, 1_000_000.0)
    return full, tradable, resolved


@pytest.mark.filterwarnings("ignore:Converting to PeriodArray")
def test_calendar_anomaly_detects_february_strength(seasonal) -> None:
    full, tradable, resolved = seasonal
    out = adc.scan_calendar_anomaly_candidates(full, tradable, resolved)
    assert [c["symbol"] for c in out] == ["SEAS"]
    cand = out[0]
    assert cand["hypothesis_type"] == "calendar_anomaly"
    assert cand["mechanism_tag"] == "risk_premium"
    assert cand["conditions"][0] == "month=2"
    assert cand["conditions"][2] == "win_rate=1.0"
    assert float(cand["conditions"][1].split("=")[1]) >= 0.025
    assert int(cand["conditions"][3].split("=")[1]) >= 6
    assert 0 < cand["priority_score"] <= 100


@pytest.mark.filterwarnings("ignore:Converting to PeriodArray")
def test_calendar_anomaly_empty_cases(seasonal, market) -> None:
    full, tradable, resolved = seasonal
    # Symbol not in today's tradable universe is skipped.
    other = tradable[tradable["symbol"] != "SEAS"]
    assert adc.scan_calendar_anomaly_candidates(full, other, resolved) == []
    # A different month has no consistent strength.
    assert adc.scan_calendar_anomaly_candidates(full, tradable, date(2026, 7, 15)) == []
    # Too little history: one February sample only.
    assert adc.scan_calendar_anomaly_candidates(market["full"], market["tradable"], AS_OF) == []
    assert adc.scan_calendar_anomaly_candidates(full, tradable, resolved, top_n=0) == []


# --- optional tables ------------------------------------------------------------


def test_read_optional_table_formats(tmp_path: Path) -> None:
    assert adc.read_optional_table(None) is None
    with pytest.raises(adc.AutoDetectError, match="optional data file not found"):
        adc.read_optional_table(tmp_path / "missing.csv")

    df = pd.DataFrame({"symbol": ["A"], "close": [1.0]})
    csv_path = tmp_path / "t.CSV"
    df.to_csv(csv_path, index=False)
    assert adc.read_optional_table(csv_path).equals(df)
    pq_path = tmp_path / "t.pq"
    df.to_parquet(pq_path)
    assert adc.read_optional_table(pq_path).equals(df)

    txt = tmp_path / "t.txt"
    txt.write_text("x", encoding="utf-8")
    with pytest.raises(adc.AutoDetectError, match="unsupported optional data format"):
        adc.read_optional_table(txt)


def test_scan_news_reaction_edge_cases() -> None:
    assert adc.scan_news_reaction_candidates(None, AS_OF) == ([], False)

    with pytest.raises(adc.AutoDetectError, match="must include symbol,timestamp,reaction_1d"):
        adc.scan_news_reaction_candidates(pd.DataFrame({"symbol": ["A"]}), AS_OF)

    other_day = pd.DataFrame({"Symbol": ["a"], "Timestamp": ["2026-01-02"], "Reaction_1D": [0.2]})
    assert adc.scan_news_reaction_candidates(other_day, AS_OF) == ([], True)

    nan_only = pd.DataFrame(
        {"symbol": ["A"], "timestamp": ["2026-02-20"], "reaction_1d": [float("nan")]}
    )
    assert adc.scan_news_reaction_candidates(nan_only, AS_OF) == ([], True)


def test_scan_news_reaction_ranks_by_magnitude_and_scores() -> None:
    news = pd.DataFrame(
        {
            "symbol": ["small", "big", "mid"],
            "timestamp": ["2026-02-20"] * 3,
            "reaction_1d": [0.03, -0.20, 0.06],
        }
    )
    out, available = adc.scan_news_reaction_candidates(news, AS_OF, top_n=2)
    assert available is True
    assert [c["symbol"] for c in out] == ["BIG", "MID"]
    # |0.20|/0.12 clamps to 1 -> 70 + 20 = 90; 0.06/0.12 = 0.5 -> 35 + 20 = 55
    assert [c["priority_score"] for c in out] == [90.0, 55.0]
    assert out[0]["reaction_1d"] == -0.20
    assert out[0]["holding_horizon"] == "10D"
    assert adc.scan_news_reaction_candidates(news, AS_OF, top_n=0) == ([], True)


# --- futures --------------------------------------------------------------------


def _futures_frame(shock_symbols: tuple[str, ...] = ("ES", "NQ")) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    dates = pd.bdate_range(end="2026-02-20", periods=70, tz="UTC")
    rows = []
    for sym in ("ES", "NQ", "CL"):
        rets = rng.normal(0.0, 0.002, len(dates))
        if sym in shock_symbols:
            rets[-1] = 0.05
        closes = 100.0 * np.cumprod(1 + rets)
        rows += [{"symbol": sym.lower(), "timestamp": d, "close": c} for d, c in zip(dates, closes)]
    return pd.DataFrame(rows)


def test_futures_trigger_maps_shocks_to_equities() -> None:
    mapping = {"ES": ["brk", "pan"], "CL": ["XOM"]}
    out, available = adc.scan_futures_trigger_candidates(_futures_frame(), mapping, AS_OF)
    assert available is True
    # NQ shock has no mapping; CL has a mapping but no shock.
    assert sorted(c["symbol"] for c in out) == ["BRK", "PAN"]
    for cand in out:
        assert cand["hypothesis_type"] == "futures_trigger"
        assert cand["entry_family"] is None
        assert cand["conditions"][0] == "future=ES"
        z = float(cand["conditions"][1].split("=")[1])
        assert z >= 2.0
        assert cand["priority_score"] == pytest.approx(min(z / 4.0, 1.0) * 60.0 + 20.0, abs=0.01)
    assert (
        len(adc.scan_futures_trigger_candidates(_futures_frame(), mapping, AS_OF, top_n=1)[0]) == 1
    )


def test_futures_trigger_edge_cases() -> None:
    assert adc.scan_futures_trigger_candidates(None, None, AS_OF) == ([], False)
    with pytest.raises(
        adc.AutoDetectError, match="futures file must include symbol,timestamp,close"
    ):
        adc.scan_futures_trigger_candidates(pd.DataFrame({"symbol": ["ES"]}), {}, AS_OF)
    assert adc.scan_futures_trigger_candidates(
        _futures_frame(), {"ES": ["A"]}, date(2020, 1, 1)
    ) == (
        [],
        True,
    )
    # No mapping at all -> shocks are ignored.
    assert adc.scan_futures_trigger_candidates(_futures_frame(), None, AS_OF) == ([], True)


def test_load_futures_map_variants(tmp_path: Path) -> None:
    assert adc.load_futures_map(None) is None
    with pytest.raises(adc.AutoDetectError, match="futures map file not found"):
        adc.load_futures_map(tmp_path / "nope.yaml")

    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    assert adc.load_futures_map(empty) == {}

    wrapped = tmp_path / "wrapped.yaml"
    wrapped.write_text(
        yaml.safe_dump(
            {"mappings": {"es": ["spy", " ", 3, "qqq"], "cl": "xom", "gc": [], 5: ["x"]}}
        ),
        encoding="utf-8",
    )
    assert adc.load_futures_map(wrapped) == {"ES": ["SPY", "QQQ"]}

    flat = tmp_path / "flat.yaml"
    flat.write_text("nq: [nvda]\n", encoding="utf-8")
    assert adc.load_futures_map(flat) == {"NQ": ["NVDA"]}

    bad = tmp_path / "bad.yaml"
    bad.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(adc.AutoDetectError, match="futures map must be a mapping"):
        adc.load_futures_map(bad)
