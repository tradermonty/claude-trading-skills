"""
Tests for generate_histogram_html.py

Tests HTML generation and data processing for visualization.
"""

import pytest
from generate_histogram_html import (
    find_latest_json,
    generate_html,
    generate_sector_options,
)


class TestGenerateSectorOptions:
    """Tests for sector dropdown generation."""

    def test_single_sector(self):
        """Test single sector option generation."""
        downtrends = [{"sector": "Technology"}]
        options = generate_sector_options(downtrends)

        assert "Technology" in options
        assert "<option" in options

    def test_multiple_sectors(self):
        """Test multiple sector options sorted alphabetically."""
        downtrends = [
            {"sector": "Technology"},
            {"sector": "Healthcare"},
            {"sector": "Energy"},
        ]
        options = generate_sector_options(downtrends)

        assert "Technology" in options
        assert "Healthcare" in options
        assert "Energy" in options
        # Check alphabetical order
        assert options.index("Energy") < options.index("Healthcare")
        assert options.index("Healthcare") < options.index("Technology")

    def test_duplicate_sectors(self):
        """Test that duplicate sectors are deduplicated."""
        downtrends = [
            {"sector": "Technology"},
            {"sector": "Technology"},
            {"sector": "Healthcare"},
        ]
        options = generate_sector_options(downtrends)

        # Count occurrences - should be 1 option tag for Technology
        assert options.count("<option") == 2  # Healthcare + Technology only

    def test_unknown_sector(self):
        """Test handling of missing sector data."""
        downtrends = [{"symbol": "ABC"}]  # No sector field
        options = generate_sector_options(downtrends)

        assert "Unknown" in options


class TestGenerateHtml:
    """Tests for HTML generation."""

    @pytest.fixture
    def sample_data(self):
        """Sample analysis data for testing."""
        return {
            "schema_version": "1.0",
            "analysis_date": "2026-03-28T07:00:00Z",
            "parameters": {
                "lookback_years": 5,
                "sector_filter": None,
                "peak_window": 20,
                "trough_window": 20,
                "min_depth_pct": 5.0,
            },
            "summary": {
                "total_downtrends": 100,
                "median_duration_days": 18,
                "mean_duration_days": 24.5,
                "p25_duration_days": 10,
                "p75_duration_days": 32,
                "p90_duration_days": 55,
            },
            "downtrends": [
                {
                    "symbol": "AAPL",
                    "sector": "Technology",
                    "market_cap_tier": "Mega",
                    "peak_date": "2025-01-15",
                    "trough_date": "2025-02-10",
                    "duration_days": 18,
                    "depth_pct": -12.5,
                },
                {
                    "symbol": "JNJ",
                    "sector": "Healthcare",
                    "market_cap_tier": "Large",
                    "peak_date": "2025-02-01",
                    "trough_date": "2025-02-20",
                    "duration_days": 14,
                    "depth_pct": -8.3,
                },
            ],
        }

    def test_html_contains_plotly(self, sample_data):
        """Test that generated HTML includes Plotly.js."""
        html = generate_html(sample_data)

        assert "plotly" in html.lower()
        assert "cdn.plot.ly" in html

    def test_html_contains_analysis_date(self, sample_data):
        """Test that analysis date is included."""
        html = generate_html(sample_data)

        assert "2026-03-28" in html

    def test_html_contains_total_count(self, sample_data):
        """Test that total downtrend count is included."""
        html = generate_html(sample_data)

        assert "100" in html  # total_downtrends

    def test_html_contains_sector_options(self, sample_data):
        """Test that sector filter options are generated."""
        html = generate_html(sample_data)

        assert "Technology" in html
        assert "Healthcare" in html

    def test_html_contains_downtrend_data(self, sample_data):
        """Test that downtrend data is embedded as JSON."""
        html = generate_html(sample_data)

        assert "AAPL" in html
        assert "duration_days" in html

    def test_html_is_valid_structure(self, sample_data):
        """Test that HTML has valid structure."""
        html = generate_html(sample_data)

        assert html.startswith("<!DOCTYPE html>")
        assert "<html" in html
        assert "</html>" in html
        assert "<head>" in html
        assert "</head>" in html
        assert "<body>" in html
        assert "</body>" in html


class TestFindLatestJson:
    """Tests for JSON file finding logic."""

    def test_direct_path(self, tmp_path):
        """Test finding a directly specified file."""
        json_file = tmp_path / "test.json"
        json_file.write_text('{"test": true}')

        result = find_latest_json(str(json_file), tmp_path)

        assert result == json_file

    def test_glob_pattern(self, tmp_path):
        """Test finding files with glob pattern."""
        # Create multiple JSON files
        (tmp_path / "analysis_2026-01-01.json").write_text('{"date": "2026-01-01"}')
        (tmp_path / "analysis_2026-02-01.json").write_text('{"date": "2026-02-01"}')

        result = find_latest_json(str(tmp_path / "analysis_*.json"), tmp_path)

        # Should find the latest (alphabetically last) file
        assert result is not None
        assert "2026-02-01" in str(result)

    def test_no_match(self, tmp_path):
        """Test behavior when no files match."""
        result = find_latest_json(str(tmp_path / "nonexistent_*.json"), tmp_path)

        assert result is None

    def test_nonexistent_direct_path(self, tmp_path):
        """Test behavior when direct path doesn't exist."""
        result = find_latest_json(str(tmp_path / "nonexistent.json"), tmp_path)

        assert result is None
