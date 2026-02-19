"""Filter tests for data_quality module.

Tests ETF exclusion, inactive stock exclusion, acquired stock exclusion,
and share class deduplication.
"""

import pytest
from data_quality import is_tradable_stock, deduplicate_share_classes, _get_share_class_group


class TestIsTradableStock:
    """is_tradable_stock filters out ETFs, inactive stocks, and acquired companies."""

    def test_normal_stock_is_tradable(self):
        profile = {
            "symbol": "AAPL",
            "companyName": "Apple Inc.",
            "isEtf": False,
            "isActivelyTrading": True,
            "isFund": False,
        }
        assert is_tradable_stock(profile) is True

    def test_etf_excluded(self):
        profile = {
            "symbol": "SPY",
            "companyName": "SPDR S&P 500 ETF Trust",
            "isEtf": True,
            "isActivelyTrading": True,
            "isFund": False,
        }
        assert is_tradable_stock(profile) is False

    def test_fund_excluded(self):
        profile = {
            "symbol": "VFINX",
            "companyName": "Vanguard 500 Index Fund",
            "isEtf": False,
            "isActivelyTrading": True,
            "isFund": True,
        }
        assert is_tradable_stock(profile) is False

    def test_inactive_stock_excluded(self):
        profile = {
            "symbol": "ATVI",
            "companyName": "Activision Blizzard",
            "isEtf": False,
            "isActivelyTrading": False,
            "isFund": False,
        }
        assert is_tradable_stock(profile) is False

    def test_missing_fields_defaults_to_tradable(self):
        """If fields are missing, assume tradable (don't over-filter)."""
        profile = {"symbol": "NEWCO", "companyName": "New Company"}
        assert is_tradable_stock(profile) is True

    def test_empty_profile_is_not_tradable(self):
        assert is_tradable_stock({}) is False

    def test_empty_symbol_is_not_tradable(self):
        profile = {"symbol": "", "companyName": "No Symbol"}
        assert is_tradable_stock(profile) is False


class TestDeduplicateShareClasses:
    """deduplicate_share_classes removes duplicate share classes like BRK-A/B."""

    def test_brk_dedup_keeps_higher_market_cap(self):
        results = [
            {"symbol": "BRK-A", "market_cap": 800_000_000_000, "percent_change": 5.0},
            {"symbol": "BRK-B", "market_cap": 800_000_000_000, "percent_change": 5.1},
            {"symbol": "AAPL", "market_cap": 3_000_000_000_000, "percent_change": 2.0},
        ]
        deduped = deduplicate_share_classes(results)
        symbols = [r["symbol"] for r in deduped]
        assert "AAPL" in symbols
        # Only one BRK variant should remain
        brk_count = sum(1 for s in symbols if s.startswith("BRK"))
        assert brk_count == 1

    def test_pbr_dedup(self):
        results = [
            {"symbol": "PBR", "market_cap": 100_000_000_000, "percent_change": 3.0},
            {"symbol": "PBR-A", "market_cap": 100_000_000_000, "percent_change": 3.2},
        ]
        deduped = deduplicate_share_classes(results)
        assert len(deduped) == 1

    def test_no_duplicates_unchanged(self):
        results = [
            {"symbol": "AAPL", "market_cap": 3_000_000_000_000, "percent_change": 2.0},
            {"symbol": "MSFT", "market_cap": 2_500_000_000_000, "percent_change": 1.5},
        ]
        deduped = deduplicate_share_classes(results)
        assert len(deduped) == 2

    def test_empty_list(self):
        assert deduplicate_share_classes([]) == []

    def test_goog_googl_dedup(self):
        results = [
            {"symbol": "GOOG", "market_cap": 2_000_000_000_000, "percent_change": 1.0},
            {"symbol": "GOOGL", "market_cap": 2_000_000_000_000, "percent_change": 1.1},
        ]
        deduped = deduplicate_share_classes(results)
        assert len(deduped) == 1


class TestShareClassGroupRegex:
    """Regression tests for SHARE_CLASS_GROUPS regex patterns."""

    def test_lbtya_matches(self):
        assert _get_share_class_group("LBTYA") == "LBTY"

    def test_lbtyb_matches(self):
        assert _get_share_class_group("LBTYB") == "LBTY"

    def test_lbtyk_matches(self):
        assert _get_share_class_group("LBTYK") == "LBTY"

    def test_lbtya_extra_no_match(self):
        """Symbols with extra chars must NOT match (anchor regression)."""
        assert _get_share_class_group("LBTYA_EXTRA") == ""

    def test_disca_matches(self):
        assert _get_share_class_group("DISCA") == "DISC"

    def test_discb_matches(self):
        assert _get_share_class_group("DISCB") == "DISC"

    def test_disck_matches(self):
        assert _get_share_class_group("DISCK") == "DISC"

    def test_disca_extra_no_match(self):
        """Symbols with extra chars must NOT match (anchor regression)."""
        assert _get_share_class_group("DISCA_EXTRA") == ""

    def test_brk_a_matches(self):
        assert _get_share_class_group("BRK-A") == "BRK"

    def test_brk_b_matches(self):
        assert _get_share_class_group("BRK-B") == "BRK"

    def test_goog_matches(self):
        assert _get_share_class_group("GOOG") == "GOOG"

    def test_googl_matches(self):
        assert _get_share_class_group("GOOGL") == "GOOG"

    def test_viaca_matches(self):
        assert _get_share_class_group("VIACA") == "VIAC"

    def test_viac_matches(self):
        assert _get_share_class_group("VIAC") == "VIAC"

    def test_viaca_extra_no_match(self):
        """Symbols with extra chars must NOT match (anchor regression)."""
        assert _get_share_class_group("VIACA_EXTRA") == ""

    def test_unrelated_symbol_no_match(self):
        assert _get_share_class_group("AAPL") == ""
