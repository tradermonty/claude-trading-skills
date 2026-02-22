"""Tests for build_sop_plan.py."""

import json
from pathlib import Path

from build_sop_plan import load_candidates, parse_ticker_csv, render_markdown


def test_parse_ticker_csv_normalizes_and_deduplicates() -> None:
    tickers = parse_ticker_csv("jnj, PG, jnj,  ko ")
    assert tickers == ["JNJ", "PG", "KO"]


def test_load_candidates_from_json_with_bucket(tmp_path: Path) -> None:
    payload = {
        "profile": "income_now",
        "candidates": [{"ticker": "jnj", "bucket": "core"}, {"ticker": "o", "bucket": "satellite"}],
    }
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(payload))
    candidates, profile = load_candidates(input_path, None)
    assert profile == "income_now"
    assert candidates == [
        {"ticker": "JNJ", "bucket": "core"},
        {"ticker": "O", "bucket": "satellite"},
    ]


def test_load_candidates_from_ticker_csv() -> None:
    candidates, profile = load_candidates(None, "aapl,msft")
    assert profile == "balanced"
    assert candidates == [
        {"ticker": "AAPL", "bucket": "unassigned"},
        {"ticker": "MSFT", "bucket": "unassigned"},
    ]


def test_render_markdown_contains_expected_sections() -> None:
    markdown = render_markdown(
        candidates=[{"ticker": "JNJ", "bucket": "core"}],
        as_of="2026-02-22",
        profile="balanced",
    )
    assert "# Kanchi SOP Plan" in markdown
    assert "## Candidate Universe" in markdown
    assert "| JNJ | core |" in markdown
