"""Tests for Theme Detector history metrics."""

import json

from theme_history import (
    append_observations,
    build_observation,
    compute_history_metrics,
    load_history,
    save_history,
)


def test_history_metrics_use_prior_observations_only():
    history = {
        "AI": [
            {"date": "2026-07-01", "heat": 40},
            {"date": "2026-07-02", "heat": 50},
            {"date": "2026-07-03", "heat": 60},
        ]
    }
    metrics = compute_history_metrics(history, "AI", "2026-07-04", 70)
    assert metrics["prior_observations"] == 3
    assert metrics["duration_count"] == 4
    assert metrics["duration_score"] == 40.0
    assert metrics["heat_delta_1d"] == 10


def test_current_date_record_is_not_self_referenced():
    history = {
        "AI": [
            {"date": "2026-07-03", "heat": 60},
            {"date": "2026-07-04", "heat": 99},
        ]
    }
    metrics = compute_history_metrics(history, "AI", "2026-07-04", 70)
    assert metrics["prior_observations"] == 1
    assert metrics["heat_delta_1d"] == 10


def test_save_and_load_history_roundtrip(tmp_path):
    path = tmp_path / "history.json"
    history = append_observations(
        {},
        [
            {
                "date": "2026-07-04",
                "theme": "AI",
                "heat": 70,
                "leadership_counts": {"ep9m": 2},
            }
        ],
    )
    save_history(str(path), history)
    loaded = load_history(str(path))
    assert loaded["AI"][0]["leadership_counts"]["ep9m"] == 2


def test_build_observation_contains_leadership_counts():
    observation = build_observation(
        {
            "name": "AI",
            "direction": "bullish",
            "heat": 70,
            "base_heat": 65,
            "leadership_score": 80,
            "leadership_counts": {"ep9m": 2},
        },
        "2026-07-04",
    )
    assert observation["date"] == "2026-07-04"
    assert observation["theme"] == "AI"
    assert observation["leadership_counts"] == {"ep9m": 2}


def test_load_history_accepts_flat_list(tmp_path):
    path = tmp_path / "history.json"
    path.write_text(json.dumps([{"date": "2026-07-04", "theme": "AI", "heat": 70}]))
    assert load_history(str(path))["AI"][0]["heat"] == 70
