"""Tests for stock leadership scan-hit detection and aggregation."""

import json

from leadership import (
    aggregate_leadership,
    blend_theme_heat,
    calculate_leadership_score,
    detect_scan_hits_from_row,
    load_scan_hits,
)


def test_raw_row_expands_to_multiple_scan_hits():
    row = {
        "date": "2026-07-04",
        "symbol": "NVDA",
        "return_5d": 24,
        "change_pct": 7,
        "volume": 12_000_000,
        "avg_volume_50d": 4_000_000,
        "true_range": 6,
        "atr_20": 3,
        "close_location": 0.9,
        "new_high": True,
        "rs_rating": 95,
        "industry": "Semiconductors",
    }
    hits = detect_scan_hits_from_row(row, "2026-07-04")
    scan_types = {hit.scan_type for hit in hits}
    assert scan_types == {
        "five_day_20pct",
        "ep9m",
        "range_expansion",
        "new_high",
        "high_rs",
    }


def test_load_scan_hits_accepts_prelabeled_json(tmp_path):
    path = tmp_path / "scan_hits.json"
    path.write_text(
        json.dumps(
            [
                {
                    "date": "2026-07-04",
                    "symbol": "CCJ",
                    "scan_type": "ep9m,range_expansion",
                    "theme_guess": "Nuclear & Uranium",
                }
            ]
        )
    )
    hits, summary = load_scan_hits(str(path), "2026-07-04")
    assert summary["rows"] == 1
    assert summary["hits"] == 2
    assert {hit.scan_type for hit in hits} == {"ep9m", "range_expansion"}


def test_load_scan_hits_filters_non_run_date_rows(tmp_path):
    path = tmp_path / "scan_hits.json"
    path.write_text(
        json.dumps(
            [
                {
                    "date": "2026-07-03",
                    "symbol": "NVDA",
                    "scan_type": "five_day_20pct",
                    "theme_guess": "AI & Semiconductors",
                },
                {
                    "date": "2026-07-04",
                    "symbol": "AVGO",
                    "scan_type": "ep9m",
                    "theme_guess": "AI & Semiconductors",
                },
                {
                    "symbol": "AMD",
                    "scan_type": "range_expansion",
                    "theme_guess": "AI & Semiconductors",
                },
            ]
        )
    )

    hits, summary = load_scan_hits(str(path), "2026-07-04")

    assert summary["rows"] == 3
    assert summary["skipped_date_rows"] == 1
    assert [hit.symbol for hit in hits] == ["AVGO", "AMD"]
    assert [hit.date for hit in hits] == ["2026-07-04", "2026-07-04"]


def test_detect_scan_hits_ignores_stale_row_date():
    hits = detect_scan_hits_from_row(
        {"date": "2026-07-03", "symbol": "NVDA", "return_5d": 25},
        "2026-07-04",
    )

    assert hits == []


def test_aggregate_leadership_scores_theme_hits():
    themes = [
        {
            "theme_name": "AI & Semiconductors",
            "matching_industries": [{"name": "Semiconductors"}],
            "static_stocks": ["NVDA"],
        }
    ]
    hits = detect_scan_hits_from_row(
        {
            "symbol": "NVDA",
            "return_5d": 25,
            "change_pct": 6,
            "volume": 10_000_000,
            "relative_volume": 2.5,
            "atr_expansion": 1.8,
            "close_location": 0.8,
            "industry": "Semiconductors",
        },
        "2026-07-04",
    )
    result = aggregate_leadership(themes, hits, history={})
    evidence = result["AI & Semiconductors"]
    assert evidence["leadership_score"] is not None
    assert evidence["leadership_coverage"] == 1.0
    assert evidence["leadership_counts"]["five_day_20pct"] == 1
    assert evidence["leadership_counts"]["ep9m"] == 1
    assert evidence["leadership_counts"]["range_expansion"] == 1
    assert evidence["leader_symbols"] == ["NVDA"]


def test_missing_leadership_does_not_depress_heat():
    assert blend_theme_heat(72.0, None) == 72.0
    assert blend_theme_heat(70.0, 100.0) == 79.0


def test_high_rs_only_hit_is_scored_not_punitive():
    themes = [
        {
            "theme_name": "AI & Semiconductors",
            "matching_industries": [{"name": "Semiconductors"}],
            "static_stocks": ["NVDA"],
        }
    ]
    hits = detect_scan_hits_from_row(
        {"symbol": "NVDA", "rs_rating": 95, "industry": "Semiconductors"},
        "2026-07-04",
    )
    result = aggregate_leadership(themes, hits, history={})
    score = result["AI & Semiconductors"]["leadership_score"]
    assert score is not None
    assert score == 7.5
    assert blend_theme_heat(70.0, score) >= 70.0


def test_leadership_weights_distinguish_sparse_evidence():
    high_rs_only = calculate_leadership_score(
        "AI & Semiconductors",
        {
            "five_day_20pct": 0,
            "ep9m": 0,
            "range_expansion": 0,
            "new_high": 0,
            "high_rs": 1,
        },
        history={},
    )
    five_day_only = calculate_leadership_score(
        "AI & Semiconductors",
        {
            "five_day_20pct": 1,
            "ep9m": 0,
            "range_expansion": 0,
            "new_high": 0,
            "high_rs": 0,
        },
        history={},
    )
    all_once = calculate_leadership_score(
        "AI & Semiconductors",
        {
            "five_day_20pct": 1,
            "ep9m": 1,
            "range_expansion": 1,
            "new_high": 1,
            "high_rs": 1,
        },
        history={},
    )

    assert high_rs_only == 7.5
    assert five_day_only == 22.5
    assert all_once == 75.0
    assert high_rs_only < five_day_only < all_once
    assert blend_theme_heat(70.0, high_rs_only) == 70.0
    assert blend_theme_heat(70.0, all_once) == 71.5
