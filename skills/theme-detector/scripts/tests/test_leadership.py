"""Tests for stock leadership scan-hit detection and aggregation."""

import json

from leadership import (
    aggregate_leadership,
    blend_theme_heat,
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
    assert score > 70
    assert blend_theme_heat(70.0, score) >= 70.0
