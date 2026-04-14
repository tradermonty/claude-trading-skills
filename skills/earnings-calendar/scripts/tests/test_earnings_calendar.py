"""Tests for Earnings Calendar scripts.

Covers:
- FMPEarningsCalendar helper methods (no API calls)
- Date validation
- Report generation (generate_report.py pure functions)
"""

import pytest
from fetch_earnings_fmp import FMPEarningsCalendar, validate_date
from generate_report import (
    calculate_summary_stats,
    format_revenue,
    generate_report,
    get_day_name,
    group_by_date,
)

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def client():
    """FMP client with dummy API key (no API calls made)."""
    return FMPEarningsCalendar(api_key="dummy-key")


@pytest.fixture
def sample_earnings():
    """Sample earnings data for testing."""
    return [
        {
            "symbol": "AAPL",
            "companyName": "Apple Inc.",
            "date": "2025-11-05",
            "timing": "AMC",
            "marketCap": 3_000_000_000_000,
            "marketCapFormatted": "$3.0T",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "epsEstimated": 1.55,
            "revenueEstimated": 89_500_000_000,
            "exchange": "NASDAQ",
        },
        {
            "symbol": "MSFT",
            "companyName": "Microsoft Corp",
            "date": "2025-11-04",
            "timing": "BMO",
            "marketCap": 2_500_000_000_000,
            "marketCapFormatted": "$2.5T",
            "sector": "Technology",
            "industry": "Software",
            "epsEstimated": 2.80,
            "revenueEstimated": 60_000_000_000,
            "exchange": "NASDAQ",
        },
        {
            "symbol": "JNJ",
            "companyName": "Johnson & Johnson",
            "date": "2025-11-04",
            "timing": "BMO",
            "marketCap": 400_000_000_000,
            "marketCapFormatted": "$400.0B",
            "sector": "Healthcare",
            "industry": "Drug Manufacturers",
            "epsEstimated": 2.60,
            "revenueEstimated": 22_000_000_000,
            "exchange": "NYSE",
        },
    ]


# ── normalize_timing ──────────────────────────────────────────────────


class TestNormalizeTiming:
    def test_bmo_variants(self, client):
        assert client.normalize_timing("bmo") == "BMO"
        assert client.normalize_timing("pre-market") == "BMO"
        assert client.normalize_timing("before market open") == "BMO"

    def test_amc_variants(self, client):
        assert client.normalize_timing("amc") == "AMC"
        assert client.normalize_timing("after-market") == "AMC"
        assert client.normalize_timing("after market close") == "AMC"

    def test_none_returns_tas(self, client):
        assert client.normalize_timing(None) == "TAS"

    def test_unknown_returns_tas(self, client):
        assert client.normalize_timing("unknown") == "TAS"
        assert client.normalize_timing("") == "TAS"


# ── format_market_cap ─────────────────────────────────────────────────


class TestFormatMarketCap:
    def test_trillion(self, client):
        assert client.format_market_cap(3_000_000_000_000) == "$3.0T"
        assert client.format_market_cap(1_500_000_000_000) == "$1.5T"

    def test_billion(self, client):
        assert client.format_market_cap(150_000_000_000) == "$150.0B"
        assert client.format_market_cap(2_000_000_000) == "$2.0B"

    def test_million(self, client):
        assert client.format_market_cap(500_000_000) == "$500M"

    def test_small(self, client):
        assert client.format_market_cap(999_999) == "$999,999"


# ── filter_by_market_cap ──────────────────────────────────────────────


class TestFilterByMarketCap:
    def test_filters_below_2b(self, client):
        earnings = [
            {"symbol": "BIG"},
            {"symbol": "SMALL"},
        ]
        profiles = {
            "BIG": {"marketCap": 10_000_000_000, "exchange": "NYSE"},
            "SMALL": {"marketCap": 500_000_000, "exchange": "NYSE"},
        }
        result = client.filter_by_market_cap(earnings, profiles)
        assert len(result) == 1
        assert result[0]["symbol"] == "BIG"

    def test_filters_non_us_exchanges(self, client):
        earnings = [{"symbol": "US"}, {"symbol": "UK"}]
        profiles = {
            "US": {"marketCap": 5_000_000_000, "exchange": "NYSE"},
            "UK": {"marketCap": 5_000_000_000, "exchange": "LSE"},
        }
        result = client.filter_by_market_cap(earnings, profiles)
        assert len(result) == 1
        assert result[0]["symbol"] == "US"

    def test_no_profile_excluded(self, client):
        earnings = [{"symbol": "NOPROFILE"}]
        profiles = {}
        result = client.filter_by_market_cap(earnings, profiles)
        assert len(result) == 0

    def test_enriches_with_profile_data(self, client):
        earnings = [{"symbol": "AAPL"}]
        profiles = {
            "AAPL": {
                "marketCap": 3_000_000_000_000,
                "companyName": "Apple Inc.",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "exchange": "NASDAQ",
            },
        }
        result = client.filter_by_market_cap(earnings, profiles)
        assert result[0]["companyName"] == "Apple Inc."
        assert result[0]["sector"] == "Technology"


# ── sort_earnings ─────────────────────────────────────────────────────


class TestSortEarnings:
    def test_sorted_by_date_then_timing_then_mcap(self, client):
        earnings = [
            {"date": "2025-11-05", "timing": "AMC", "marketCap": 100},
            {"date": "2025-11-04", "timing": "BMO", "marketCap": 200},
            {"date": "2025-11-04", "timing": "AMC", "marketCap": 300},
            {"date": "2025-11-04", "timing": "BMO", "marketCap": 500},
        ]
        result = client.sort_earnings(earnings)
        # 2025-11-04 first, BMO before AMC, higher mcap first within BMO
        assert result[0]["date"] == "2025-11-04"
        assert result[0]["timing"] == "BMO"
        assert result[0]["marketCap"] == 500
        assert result[1]["timing"] == "BMO"
        assert result[1]["marketCap"] == 200
        assert result[2]["timing"] == "AMC"


# ── validate_date ─────────────────────────────────────────────────────


class TestValidateDate:
    def test_valid_date(self):
        assert validate_date("2025-11-04") is True

    def test_invalid_format(self):
        assert validate_date("11-04-2025") is False
        assert validate_date("2025/11/04") is False

    def test_invalid_date(self):
        assert validate_date("2025-13-01") is False
        assert validate_date("not-a-date") is False


# ── Report generation helpers ─────────────────────────────────────────


class TestGroupByDate:
    def test_groups_correctly(self, sample_earnings):
        result = group_by_date(sample_earnings)
        assert "2025-11-04" in result
        assert "2025-11-05" in result
        assert len(result["2025-11-04"]["BMO"]) == 2
        assert len(result["2025-11-05"]["AMC"]) == 1

    def test_empty_input(self):
        assert group_by_date([]) == {}


class TestFormatRevenue:
    def test_trillion(self):
        assert format_revenue(1_500_000_000_000) == "$1.5T"

    def test_billion(self):
        assert format_revenue(89_500_000_000) == "$89.5B"

    def test_million(self):
        assert format_revenue(500_000_000) == "$500M"


class TestGetDayName:
    def test_known_date(self):
        result = get_day_name("2025-11-04")
        assert "Tuesday" in result
        assert "November" in result


class TestCalculateSummaryStats:
    def test_stats(self, sample_earnings):
        stats = calculate_summary_stats(sample_earnings)
        assert stats["total"] == 3
        assert stats["large_cap"] == 3  # all > $10B
        assert stats["mid_cap"] == 0
        assert stats["sectors"]["Technology"] == 2
        assert stats["sectors"]["Healthcare"] == 1
        assert stats["peak_count"] == 2  # Nov 4 has 2 entries


class TestGenerateReport:
    def test_report_contains_companies(self, sample_earnings):
        report = generate_report(sample_earnings)
        assert "AAPL" in report
        assert "MSFT" in report
        assert "JNJ" in report

    def test_empty_earnings(self):
        report = generate_report([])
        assert "No earnings data available" in report

    def test_report_has_sections(self, sample_earnings):
        report = generate_report(sample_earnings)
        assert "Executive Summary" in report
        assert "Key Observations" in report
        assert "Sector Distribution" in report
