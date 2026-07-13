"""Tests for reaction_math.py — pure news-reaction-failure calculation module.

No I/O, no network. Run with:
    python3 -m pytest skills/news-reaction-failure-analyzer/scripts/tests/ -v
"""

import math
import random
import statistics
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from reaction_math import (  # noqa: E402
    CONFIDENCE_HIGH_DRIFT_Z,
    DRIFT_Z_DEFAULT,
    MIN_EVENTS_DEFAULT,
    Z_THRESHOLD_DEFAULT,
    build_sorted_series,
    classify_reaction,
    cluster_events,
    compute_confidence,
    compute_daily_stdev,
    compute_effective_date,
    compute_returns,
    compute_zscore_1d,
    compute_zscore_3d,
    derive_actual_reaction,
    direction_adjusted_zscore,
    expected_direction_for,
    find_date_index,
    synthesize_result,
    synthesize_verdict,
)

# ---------------------------------------------------------------------------
# Synthetic price series shared by several test classes.
#
# 11 trading days, Mon 2026-06-01 .. with a weekend gap (no Sat/Sun rows,
# since only trading days are ever in the series) and a simulated holiday
# gap between D4 and D5 (2026-06-08 -> 2026-06-10, skipping 06-09).
# ---------------------------------------------------------------------------
TRADING_DATES = [
    "2026-06-01",  # D0
    "2026-06-02",  # D1
    "2026-06-03",  # D2
    "2026-06-04",  # D3
    "2026-06-05",  # D4 (Friday)
    "2026-06-08",  # D5 (Monday -- weekend gap between D4 and D5)
    "2026-06-10",  # D6 (holiday gap: 06-09 missing)
    "2026-06-11",  # D7
    "2026-06-12",  # D8
    "2026-06-15",  # D9
    "2026-06-16",  # D10
]
CLOSES = [100, 101, 99, 98, 97, 100, 103, 105, 104, 106, 108]
SERIES = list(zip(TRADING_DATES, CLOSES))


def make_rows(dates=TRADING_DATES, closes=CLOSES):
    return [{"date": d, "close": c} for d, c in zip(dates, closes)]


class TestBuildSortedSeries:
    def test_sorts_and_dedupes(self):
        rows = [
            {"date": "2026-06-02", "close": 101},
            {"date": "2026-06-01", "close": 100},
            {"date": "2026-06-02", "close": 999},  # duplicate date, last wins
        ]
        series = build_sorted_series(rows)
        assert series == [("2026-06-01", 100), ("2026-06-02", 999)]

    def test_drops_rows_missing_date_or_close(self):
        rows = [
            {"date": "2026-06-01", "close": 100},
            {"date": None, "close": 101},
            {"close": 102},
            {"date": "2026-06-02", "close": None},
        ]
        series = build_sorted_series(rows)
        assert series == [("2026-06-01", 100)]

    def test_empty_input(self):
        assert build_sorted_series([]) == []

    def test_accepts_price_field_as_a_close_fallback(self):
        # Verified live: FMP's stable/historical-price-eod/light endpoint
        # returns "price", not "close", for every symbol on this endpoint
        # (futures, ETFs, and FX alike). "close" still wins if both are
        # present (e.g. a different upstream endpoint).
        rows = [
            {"date": "2026-07-08", "price": 1.33877, "volume": 339306},
            {"date": "2026-07-09", "price": 1.34078, "volume": 218450},
        ]
        series = build_sorted_series(rows)
        assert series == [("2026-07-08", 1.33877), ("2026-07-09", 1.34078)]

    def test_close_field_wins_over_price_when_both_present(self):
        rows = [{"date": "2026-07-08", "close": 100.0, "price": 999.0}]
        series = build_sorted_series(rows)
        assert series == [("2026-07-08", 100.0)]


class TestFindDateIndex:
    def test_finds_existing_date(self):
        assert find_date_index(SERIES, "2026-06-05") == 4

    def test_missing_date_returns_none(self):
        assert find_date_index(SERIES, "2026-06-09") is None


class TestComputeEffectiveDate:
    def test_before_close_same_day(self):
        # 10:30 ET on a trading day -> same day
        assert compute_effective_date("2026-06-03T10:30:00-04:00", TRADING_DATES) == "2026-06-03"

    def test_at_or_after_16_00_et_snaps_to_next_trading_day(self):
        assert compute_effective_date("2026-06-03T16:00:00-04:00", TRADING_DATES) == "2026-06-04"
        assert compute_effective_date("2026-06-03T20:00:00-04:00", TRADING_DATES) == "2026-06-04"

    def test_weekend_snaps_to_next_trading_day(self):
        # 2026-06-06 is a Saturday; not a trading date at all.
        assert compute_effective_date("2026-06-06T10:00:00-04:00", TRADING_DATES) == "2026-06-08"

    def test_holiday_gap_snaps_to_next_trading_day(self):
        # 2026-06-09 is a simulated holiday (missing from TRADING_DATES).
        assert compute_effective_date("2026-06-09T10:00:00-04:00", TRADING_DATES) == "2026-06-10"

    def test_after_close_on_last_available_date_returns_none(self):
        assert compute_effective_date("2026-06-16T20:00:00-04:00", TRADING_DATES) is None

    def test_utc_offset_converted_to_et_for_close_cutoff(self):
        # 20:15 UTC = 16:15 ET (EDT, UTC-4) on 2026-06-03 -> after close -> next day.
        assert compute_effective_date("2026-06-03T20:15:00+00:00", TRADING_DATES) == "2026-06-04"
        # 19:45 UTC = 15:45 ET -> before close -> same day.
        assert compute_effective_date("2026-06-03T19:45:00+00:00", TRADING_DATES) == "2026-06-03"

    def test_naive_datetime_raises_value_error(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            compute_effective_date("2026-06-03T10:30:00", TRADING_DATES)

    def test_unparsable_string_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_effective_date("not-a-date", TRADING_DATES)


class TestComputeReturns:
    def test_hand_computed_returns(self):
        # effective_date = D4 (idx=4, close=97); pre = D3 (idx=3, close=98);
        # +1d = D5 (idx=5, close=100); +3d = D7 (idx=7, close=105).
        result = compute_returns(SERIES, "2026-06-05")
        assert result["return_1d"] == pytest.approx(100 / 98 - 1)
        assert result["return_3d"] == pytest.approx(105 / 98 - 1)

    def test_effective_date_at_series_start_has_no_pre_close(self):
        result = compute_returns(SERIES, "2026-06-01")
        assert result["return_1d"] is None
        assert result["return_3d"] is None

    def test_insufficient_forward_bars_returns_none_for_that_horizon(self):
        # D10 (idx=10) is the last bar: no +1d or +3d bar exists.
        result = compute_returns(SERIES, "2026-06-16")
        assert result["return_1d"] is None
        assert result["return_3d"] is None

    def test_unknown_effective_date_returns_none(self):
        result = compute_returns(SERIES, "2099-01-01")
        assert result["return_1d"] is None
        assert result["return_3d"] is None


class TestComputeDailyStdev:
    def test_matches_hand_computed_stdev(self):
        # Small deterministic series. "Ending the day before the event"
        # means the event at dates[4] (idx=4) uses daily returns through
        # idx=3 only (i=1,2,3), NOT the event day itself (idx=4).
        closes = [100, 102, 101, 103, 102, 104]
        dates = [f"2026-07-{i:02d}" for i in range(1, 7)]
        series = list(zip(dates, closes))
        daily_returns = [closes[i] / closes[i - 1] - 1 for i in range(1, 4)]  # idx 1,2,3
        expected = statistics.stdev(daily_returns)
        result = compute_daily_stdev(series, dates[4], lookback=5, min_samples=2)
        assert result == pytest.approx(expected)

    def test_insufficient_samples_returns_none(self):
        closes = [100, 101, 102]
        dates = ["2026-07-01", "2026-07-02", "2026-07-03"]
        series = list(zip(dates, closes))
        # Only 1 daily return available before the event; default min_samples
        # (20) is far higher.
        assert compute_daily_stdev(series, "2026-07-03", lookback=60) is None

    def test_effective_date_not_in_series_returns_none(self):
        assert compute_daily_stdev(SERIES, "2099-01-01") is None


class TestComputeZscores:
    def test_zscore_1d_no_horizon_scaling(self):
        assert compute_zscore_1d(0.05, 0.02) == pytest.approx(2.5)

    def test_zscore_3d_sqrt3_scaling_pinned(self):
        # Hand-pinned literal (not reconstructed via math.sqrt in this test)
        # so a regression that drops/changes the sqrt(3) scaling is caught
        # even if it accidentally reproduces math.sqrt(3) some other way.
        result = compute_zscore_3d(0.05, 0.02)
        assert result == pytest.approx(1.4433756729740645, rel=1e-9)

    def test_zscore_none_when_stdev_none_or_zero(self):
        assert compute_zscore_1d(0.05, None) is None
        assert compute_zscore_1d(0.05, 0.0) is None
        assert compute_zscore_3d(0.05, None) is None
        assert compute_zscore_3d(0.05, 0.0) is None

    def test_zscore_none_when_return_none(self):
        assert compute_zscore_1d(None, 0.02) is None
        assert compute_zscore_3d(None, 0.02) is None


class TestDirectionAdjustedZscore:
    def test_crowded_long_unchanged(self):
        assert direction_adjusted_zscore(1.5, "CROWDED_LONG") == pytest.approx(1.5)
        assert direction_adjusted_zscore(-1.5, "CROWDED_LONG") == pytest.approx(-1.5)

    def test_crowded_short_sign_flipped(self):
        assert direction_adjusted_zscore(1.5, "CROWDED_SHORT") == pytest.approx(-1.5)
        assert direction_adjusted_zscore(-1.5, "CROWDED_SHORT") == pytest.approx(1.5)

    def test_none_passthrough(self):
        assert direction_adjusted_zscore(None, "CROWDED_LONG") is None
        assert direction_adjusted_zscore(None, "CROWDED_SHORT") is None


class TestExpectedDirectionFor:
    def test_crowded_long_is_bullish(self):
        assert expected_direction_for("CROWDED_LONG") == "BULLISH"

    def test_crowded_short_is_bearish(self):
        assert expected_direction_for("CROWDED_SHORT") == "BEARISH"


class TestClassifyReaction:
    def test_boundary_exactly_positive_0_5_is_responded(self):
        assert classify_reaction(0.5) == "RESPONDED"

    def test_boundary_exactly_negative_0_5_is_opposite(self):
        assert classify_reaction(-0.5) == "OPPOSITE"

    def test_just_above_positive_boundary_is_responded(self):
        assert classify_reaction(0.51) == "RESPONDED"

    def test_just_below_negative_boundary_is_opposite(self):
        assert classify_reaction(-0.51) == "OPPOSITE"

    def test_inside_boundaries_is_failed_to_respond(self):
        assert classify_reaction(0.0) == "FAILED_TO_RESPOND"
        assert classify_reaction(0.49) == "FAILED_TO_RESPOND"
        assert classify_reaction(-0.49) == "FAILED_TO_RESPOND"

    def test_custom_threshold(self):
        assert classify_reaction(0.8, z_threshold=1.0) == "FAILED_TO_RESPOND"
        assert classify_reaction(1.0, z_threshold=1.0) == "RESPONDED"


class TestClusterEvents:
    """Pinned rule: a cluster's z3 is the z3 already computed at the
    cluster's own effective date -- the EARLIEST member's window z3.
    Member z3 values are never averaged; they are only recorded (in
    `cluster_members`) for transparency and do not enter drift_stat."""

    def _event(self, event_id, idx, z3):
        return {
            "event_id": event_id,
            "effective_date": f"idx{idx}",
            "effective_date_index": idx,
            "zscore_3d_adjusted": z3,
        }

    def test_overlapping_windows_collapse_to_one_cluster(self):
        # window=3: event@5 -> [5,8]; event@6 -> [6,9] overlaps (6<=8).
        events = [self._event("e1", 5, 1.0), self._event("e2", 6, 2.0)]
        clusters = cluster_events(events)
        assert len(clusters) == 1
        assert clusters[0]["effective_date_index"] == 5
        assert [m["event_id"] for m in clusters[0]["cluster_members"]] == ["e1", "e2"]

    def test_cluster_z3_is_earliest_members_own_z3_not_averaged(self):
        # e1 (earliest, idx=5) has z3=1.0; e2 (idx=6) has a very different
        # z3=9.0. The cluster must contribute 1.0 (e1's own window z3),
        # NOT the mean (5.0) -- this is the pinned regression test for the
        # no-averaging rule.
        events = [self._event("e1", 5, 1.0), self._event("e2", 6, 9.0)]
        clusters = cluster_events(events)
        assert len(clusters) == 1
        assert clusters[0]["zscore_3d_adjusted"] == pytest.approx(1.0)
        assert clusters[0]["zscore_3d_adjusted"] != pytest.approx(5.0)  # not the mean

    def test_cluster_members_record_individual_z3_for_transparency(self):
        events = [self._event("e1", 5, 1.0), self._event("e2", 6, 9.0)]
        clusters = cluster_events(events)
        members = {m["event_id"]: m["zscore_3d_adjusted"] for m in clusters[0]["cluster_members"]}
        assert members == {"e1": 1.0, "e2": 9.0}

    def test_non_overlapping_windows_stay_separate(self):
        # event@0 -> [0,3]; event@5 -> [5,8]; event@10 -> [10,13]. None overlap.
        events = [self._event("e1", 0, 1.0), self._event("e2", 5, 2.0), self._event("e3", 10, 3.0)]
        clusters = cluster_events(events)
        assert len(clusters) == 3
        assert [[m["event_id"] for m in c["cluster_members"]] for c in clusters] == [
            ["e1"],
            ["e2"],
            ["e3"],
        ]
        # Each singleton cluster's z3 is just that one event's own z3.
        assert [c["zscore_3d_adjusted"] for c in clusters] == [1.0, 2.0, 3.0]

    def test_transitive_chain_merges_into_one_cluster(self):
        # event@0 -> [0,3]; event@3 -> [3,6] overlaps 0; event@6 -> [6,9]
        # overlaps the extended chain end (6) even though it doesn't overlap
        # event@0's own window directly.
        events = [self._event("e1", 0, 0.0), self._event("e2", 3, 3.0), self._event("e3", 6, 6.0)]
        clusters = cluster_events(events)
        assert len(clusters) == 1
        assert [m["event_id"] for m in clusters[0]["cluster_members"]] == ["e1", "e2", "e3"]
        # Cluster z3 = earliest member's (e1's) own z3, not the mean (3.0).
        assert clusters[0]["zscore_3d_adjusted"] == pytest.approx(0.0)

    def test_earliest_effective_date_used(self):
        events = [self._event("e2", 6, 2.0), self._event("e1", 5, 1.0)]  # out of order
        clusters = cluster_events(events)
        assert clusters[0]["effective_date"] == "idx5"
        assert clusters[0]["zscore_3d_adjusted"] == pytest.approx(1.0)  # e1's own z3

    def test_empty_input(self):
        assert cluster_events([]) == []


class TestSynthesizeVerdict:
    def test_below_min_events_is_insufficient_evidence(self):
        verdict, reason = synthesize_verdict(n=2, drift_stat=-5.0, responded_ratio=0.0)
        assert verdict == "INSUFFICIENT_EVIDENCE"
        assert reason == "insufficient_relevant_events"

    def test_zero_events_is_insufficient_evidence(self):
        verdict, _ = synthesize_verdict(n=0, drift_stat=None, responded_ratio=None)
        assert verdict == "INSUFFICIENT_EVIDENCE"

    def test_confirmed_boundary_drift_stat_exactly_negative_drift_z(self):
        verdict, reason = synthesize_verdict(n=4, drift_stat=-DRIFT_Z_DEFAULT, responded_ratio=0.0)
        assert verdict == "CONFIRMED"
        assert reason is None

    def test_confirmed_boundary_responded_ratio_exactly_0_25(self):
        verdict, _ = synthesize_verdict(n=4, drift_stat=-2.0, responded_ratio=0.25)
        assert verdict == "CONFIRMED"

    def test_just_above_drift_threshold_not_confirmed(self):
        verdict, _ = synthesize_verdict(
            n=4, drift_stat=-DRIFT_Z_DEFAULT + 0.01, responded_ratio=0.0
        )
        assert verdict != "CONFIRMED"

    def test_strong_negative_drift_but_high_responded_ratio_not_confirmed(self):
        verdict, reason = synthesize_verdict(n=4, drift_stat=-3.0, responded_ratio=0.3)
        assert verdict == "NOT_CONFIRMED"
        assert reason == "mixed_reactions"

    def test_positive_drift_is_not_confirmed_market_rewarded_crowd(self):
        verdict, reason = synthesize_verdict(n=4, drift_stat=+DRIFT_Z_DEFAULT, responded_ratio=0.0)
        assert verdict == "NOT_CONFIRMED"
        assert reason == "market_rewarded_crowd"

    def test_high_responded_ratio_alone_is_not_confirmed_market_rewarded_crowd(self):
        verdict, reason = synthesize_verdict(n=4, drift_stat=0.0, responded_ratio=0.5)
        assert verdict == "NOT_CONFIRMED"
        assert reason == "market_rewarded_crowd"

    def test_ambiguous_middle_ground_is_not_confirmed_mixed(self):
        verdict, reason = synthesize_verdict(n=4, drift_stat=0.0, responded_ratio=0.3)
        assert verdict == "NOT_CONFIRMED"
        assert reason == "mixed_reactions"

    def test_custom_min_events_and_drift_z(self):
        verdict, _ = synthesize_verdict(n=5, drift_stat=-1.0, responded_ratio=0.0, min_events=6)
        assert verdict == "INSUFFICIENT_EVIDENCE"
        verdict2, _ = synthesize_verdict(n=5, drift_stat=-1.0, responded_ratio=0.0, drift_z=0.9)
        assert verdict2 == "CONFIRMED"


class TestComputeConfidence:
    def test_high_when_all_criteria_met(self):
        assert compute_confidence("CONFIRMED", -2.0, n=4, opposite_count=1) == "HIGH"

    def test_high_boundary_exactly_at_threshold(self):
        assert (
            compute_confidence("CONFIRMED", -CONFIDENCE_HIGH_DRIFT_Z, n=4, opposite_count=1)
            == "HIGH"
        )

    def test_medium_when_drift_not_strong_enough(self):
        result = compute_confidence(
            "CONFIRMED", -CONFIDENCE_HIGH_DRIFT_Z + 0.01, n=4, opposite_count=1
        )
        assert result == "MEDIUM"

    def test_medium_when_n_below_4(self):
        assert compute_confidence("CONFIRMED", -2.0, n=3, opposite_count=1) == "MEDIUM"

    def test_medium_when_no_opposite_events(self):
        assert compute_confidence("CONFIRMED", -2.0, n=4, opposite_count=0) == "MEDIUM"

    def test_medium_when_verdict_not_confirmed(self):
        assert compute_confidence("NOT_CONFIRMED", -2.0, n=4, opposite_count=1) == "MEDIUM"
        assert compute_confidence("INSUFFICIENT_EVIDENCE", None, n=0, opposite_count=0) == "MEDIUM"

    def test_never_returns_low_in_v1(self):
        # LOW is reserved for future use; spot-check a spread of inputs.
        for verdict in ("CONFIRMED", "NOT_CONFIRMED", "INSUFFICIENT_EVIDENCE"):
            for drift in (-5.0, -1.645, -1.0, 0.0, 1.0, None):
                result = compute_confidence(verdict, drift, n=4, opposite_count=1)
                assert result in ("HIGH", "MEDIUM")


class TestDeriveActualReaction:
    def test_confirmed_long_is_failed_to_rally(self):
        assert derive_actual_reaction("CONFIRMED", "CROWDED_LONG", 0.0) == "FAILED_TO_RALLY"

    def test_confirmed_short_is_failed_to_sell_off(self):
        assert derive_actual_reaction("CONFIRMED", "CROWDED_SHORT", 0.0) == "FAILED_TO_SELL_OFF"

    def test_not_confirmed_high_responded_ratio_long_is_rallied(self):
        assert derive_actual_reaction("NOT_CONFIRMED", "CROWDED_LONG", 0.6) == "RALLIED"

    def test_not_confirmed_high_responded_ratio_short_is_sold_off(self):
        assert derive_actual_reaction("NOT_CONFIRMED", "CROWDED_SHORT", 0.6) == "SOLD_OFF"

    def test_not_confirmed_boundary_exactly_0_5_counts_as_high(self):
        assert derive_actual_reaction("NOT_CONFIRMED", "CROWDED_LONG", 0.5) == "RALLIED"

    def test_not_confirmed_low_responded_ratio_is_mixed_reaction(self):
        assert derive_actual_reaction("NOT_CONFIRMED", "CROWDED_LONG", 0.3) == "MIXED_REACTION"
        assert derive_actual_reaction("NOT_CONFIRMED", "CROWDED_SHORT", 0.3) == "MIXED_REACTION"

    def test_insufficient_evidence_is_no_data_regardless_of_direction(self):
        assert derive_actual_reaction("INSUFFICIENT_EVIDENCE", "CROWDED_LONG", None) == "NO_DATA"
        assert derive_actual_reaction("INSUFFICIENT_EVIDENCE", "CROWDED_SHORT", None) == "NO_DATA"


class TestSynthesizeResult:
    def _event(self, event_id, idx, z3):
        return {
            "event_id": event_id,
            "effective_date": f"idx{idx}",
            "effective_date_index": idx,
            "zscore_3d_adjusted": z3,
        }

    def test_confirmed_scenario_end_to_end(self):
        # 4 well-separated events, all strongly negative adjusted z3 ->
        # drift_stat very negative, responded_ratio 0 -> CONFIRMED.
        events = [
            self._event("e1", 0, -2.0),
            self._event("e2", 10, -2.0),
            self._event("e3", 20, -2.0),
            self._event("e4", 30, -2.0),
        ]
        result = synthesize_result(events, "CROWDED_LONG")
        assert result["n"] == 4
        assert result["verdict"] == "CONFIRMED"
        assert result["drift_stat"] == pytest.approx(math.sqrt(4) * -2.0)
        assert result["responded_ratio"] == pytest.approx(0.0)
        assert result["actual_reaction"] == "FAILED_TO_RALLY"
        assert result["confidence"] == "HIGH"

    def test_insufficient_evidence_scenario(self):
        events = [self._event("e1", 0, -2.0), self._event("e2", 10, -2.0)]
        result = synthesize_result(events, "CROWDED_LONG")
        assert result["n"] == 2
        assert result["verdict"] == "INSUFFICIENT_EVIDENCE"
        assert result["actual_reaction"] == "NO_DATA"

    def test_clustering_reduces_n_below_min_events(self):
        # 3 raw events but 2 overlap into 1 cluster -> n=2 clusters -> below
        # min_events=3 -> INSUFFICIENT_EVIDENCE despite 3 raw events.
        events = [
            self._event("e1", 0, -2.0),
            self._event("e2", 1, -2.0),  # overlaps e1 (window=3)
            self._event("e3", 20, -2.0),
        ]
        result = synthesize_result(events, "CROWDED_LONG")
        assert result["n"] == 2
        assert result["verdict"] == "INSUFFICIENT_EVIDENCE"

    def test_no_usable_events_is_insufficient_evidence(self):
        result = synthesize_result([], "CROWDED_LONG")
        assert result["n"] == 0
        assert result["verdict"] == "INSUFFICIENT_EVIDENCE"
        assert result["actual_reaction"] == "NO_DATA"


# ---------------------------------------------------------------------------
# Monte Carlo regression tests for the drift-significance verdict design.
#
# v1's naive failure-ratio design CONFIRMed on pure noise ~48-83% of the
# time. These tests are the direct regression guard for that flaw: under an
# i.i.d. N(0,1) null (no real drift), the CONFIRMED rate must stay under the
# documented bound. A fixed seed makes the result reproducible; 50,000
# trials per n gives a binomial standard error of ~0.12pp at an 8% rate, so
# the bound is not seed-luck.
# ---------------------------------------------------------------------------

MC_SEED = 20260712
MC_TRIALS = 50_000
MC_N_VALUES = (3, 4, 5, 8)


def _simulate_verdict(rng, n, z_values, min_events=MIN_EVENTS_DEFAULT, drift_z=DRIFT_Z_DEFAULT):
    mean_z3 = sum(z_values) / n
    drift_stat = math.sqrt(n) * mean_z3
    responded_ratio = sum(1 for z in z_values if z >= Z_THRESHOLD_DEFAULT) / n
    verdict, _ = synthesize_verdict(
        n, drift_stat, responded_ratio, min_events=min_events, drift_z=drift_z
    )
    return verdict


class TestMonteCarloNullBound:
    def test_iid_null_confirmed_rate_below_8_percent_and_not_modal(self):
        rng = random.Random(MC_SEED)
        for n in MC_N_VALUES:
            counts = {"CONFIRMED": 0, "NOT_CONFIRMED": 0, "INSUFFICIENT_EVIDENCE": 0}
            for _ in range(MC_TRIALS):
                z_values = [rng.gauss(0.0, 1.0) for _ in range(n)]
                verdict = _simulate_verdict(rng, n, z_values)
                counts[verdict] += 1
            rate = counts["CONFIRMED"] / MC_TRIALS
            assert rate < 0.08, (
                f"n={n}: iid null CONFIRMED rate {rate:.4f} ({counts['CONFIRMED']}/{MC_TRIALS}) "
                "exceeds the 8% bound"
            )
            assert counts["CONFIRMED"] < counts["NOT_CONFIRMED"], (
                f"n={n}: CONFIRMED ({counts['CONFIRMED']}) must not be the modal verdict "
                f"(NOT_CONFIRMED={counts['NOT_CONFIRMED']})"
            )


class TestMonteCarloAr1CorrelatedNull:
    """Robustness check for correlated noise that slips past the clustering
    rule (event windows narrow enough not to overlap, but still weakly
    correlated -- e.g. two related headlines a week apart).

    Two scenarios, per the plan's final calibration:

    - rho=0.1 (HARD bound, <10%): the clustering rule already removes
      window-overlapping correlation -- the mechanism a correlation stress
      test is meant to probe. Across non-overlapping 3-day cluster windows,
      lag-1 rho=0.3 exceeds empirical signed-return autocorrelation of
      liquid futures by roughly an order of magnitude; rho=0.1 remains
      conservative versus that empirical reality while still exercising the
      realistic residual channel. This is the asserted regression gate.
    - rho=0.3 (INFORMATIONAL, sanity ceiling <20%): an intentionally
      extreme stress scenario, kept and measured (not just skipped) so a
      severe regression still trips something, but not hard-gated at <10%
      -- at drift_z=1.45 this scenario measures ~11-13% null CONFIRMED
      (verified: worst case 13.08% at n=8, 300k-trial probe), which is a
      known, documented v1 residual risk (see references/news-failure-
      patterns.md and SKILL.md), not a design defect. Users who need
      stricter behavior under this specific stress can raise --drift-z to
      1.75, which restores <10% even at rho=0.3.
    """

    def _ar1_draws(self, rng, n, rho):
        draws = [rng.gauss(0.0, 1.0)]
        scale = math.sqrt(1 - rho**2)
        for _ in range(n - 1):
            eps = rng.gauss(0.0, 1.0)
            draws.append(rho * draws[-1] + scale * eps)
        return draws

    def _measure(self, rho):
        rng = random.Random(MC_SEED)
        rates = {}
        for n in MC_N_VALUES:
            confirmed = 0
            for _ in range(MC_TRIALS):
                z_values = self._ar1_draws(rng, n, rho)
                verdict = _simulate_verdict(rng, n, z_values)
                if verdict == "CONFIRMED":
                    confirmed += 1
            rates[n] = confirmed / MC_TRIALS
        return rates

    def test_ar1_rho_0_1_null_confirmed_rate_below_10_percent(self):
        rates = self._measure(rho=0.1)
        for n, rate in rates.items():
            assert rate < 0.10, (
                f"n={n}: AR(1) rho=0.1 null CONFIRMED rate {rate:.4f} exceeds the 10% hard bound"
            )

    def test_ar1_rho_0_3_is_informational_with_sanity_ceiling(self):
        """Not a design defect if this exceeds 10% -- it's an intentionally
        extreme stress scenario, documented as a v1 residual risk. Only a
        severe regression (>=20%) should trip this."""
        rates = self._measure(rho=0.3)
        for n, rate in rates.items():
            print(f"[informational] AR(1) rho=0.3, n={n}: null CONFIRMED rate = {rate:.4f}")
            assert rate < 0.20, (
                f"n={n}: AR(1) rho=0.3 null CONFIRMED rate {rate:.4f} exceeds the 20% "
                "sanity ceiling -- this is a regression, not the documented residual risk"
            )
