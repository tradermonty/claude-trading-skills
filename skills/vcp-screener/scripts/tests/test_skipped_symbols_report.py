"""Tests for skipped-symbol reporting in JSON and Markdown reports."""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from report_generator import generate_json_report, generate_markdown_report


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_METADATA = {
    "generated_at": "2026-01-01 00:00:00",
    "universe_description": "Custom (3 stocks)",
    "funnel": {
        "universe": 3,
        "quotes_fetched": 1,
        "symbols_skipped": 2,
        "pre_filter_passed": 1,
        "trend_template_passed": 0,
        "vcp_candidates": 0,
    },
    "api_stats": {"api_calls_made": 5, "cache_entries": 3},
}

SKIPPED = [
    {"symbol": "AVGO", "http_status": 402, "error_category": "paid_tier_required", "endpoint": "quote"},
    {"symbol": "HD",   "http_status": 402, "error_category": "paid_tier_required", "endpoint": "quote"},
]


# ---------------------------------------------------------------------------
# JSON report
# ---------------------------------------------------------------------------

class TestJsonReportSkipped:
    def test_skipped_symbols_in_json(self, tmp_path):
        out = str(tmp_path / "report.json")
        generate_json_report([], MINIMAL_METADATA, out, skipped=SKIPPED)
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        assert "skipped_symbols" in data
        assert len(data["skipped_symbols"]) == 2
        syms = [s["symbol"] for s in data["skipped_symbols"]]
        assert "AVGO" in syms
        assert "HD" in syms

    def test_empty_skipped_in_json(self, tmp_path):
        out = str(tmp_path / "report.json")
        generate_json_report([], MINIMAL_METADATA, out, skipped=[])
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        assert data["skipped_symbols"] == []

    def test_skipped_none_defaults_to_empty(self, tmp_path):
        out = str(tmp_path / "report.json")
        generate_json_report([], MINIMAL_METADATA, out, skipped=None)
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        assert data["skipped_symbols"] == []

    def test_skipped_entry_fields_preserved(self, tmp_path):
        out = str(tmp_path / "report.json")
        generate_json_report([], MINIMAL_METADATA, out, skipped=SKIPPED)
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        entry = data["skipped_symbols"][0]
        assert entry["http_status"] == 402
        assert entry["error_category"] == "paid_tier_required"


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

class TestMarkdownReportSkipped:
    def _render(self, tmp_path, skipped):
        out = str(tmp_path / "report.md")
        generate_markdown_report([], MINIMAL_METADATA, out, skipped=skipped)
        return open(out, encoding="utf-8").read()

    def test_warning_banner_present_when_skipped(self, tmp_path):
        md = self._render(tmp_path, SKIPPED)
        assert "WARNING" in md
        assert "2 symbol(s)" in md

    def test_no_warning_when_no_skipped(self, tmp_path):
        md = self._render(tmp_path, [])
        assert "WARNING" not in md

    def test_skipped_table_present(self, tmp_path):
        md = self._render(tmp_path, SKIPPED)
        assert "## Skipped Symbols" in md
        assert "AVGO" in md
        assert "HD" in md
        assert "paid_tier_required" in md

    def test_funnel_shows_skipped_row(self, tmp_path):
        md = self._render(tmp_path, SKIPPED)
        assert "Symbols skipped" in md

    def test_funnel_no_skipped_row_when_none(self, tmp_path):
        meta = dict(MINIMAL_METADATA)
        meta["funnel"] = dict(MINIMAL_METADATA["funnel"])
        meta["funnel"]["symbols_skipped"] = 0
        out = str(tmp_path / "report.md")
        generate_markdown_report([], meta, out, skipped=[])
        md = open(out, encoding="utf-8").read()
        assert "Symbols skipped" not in md

    def test_no_skipped_section_when_empty(self, tmp_path):
        md = self._render(tmp_path, [])
        assert "## Skipped Symbols" not in md
