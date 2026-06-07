"""Tests for the curated starter universe (universe.py).

Covers:
- No duplicate tickers
- No empty / whitespace-only ticker strings
- No blank sector labels
- MA is in Financials (not Information Technology)
- V is in Financials
- Universe size is approximately 100 (95–105)
- At least 8 distinct GICS sectors are represented
- validate_universe() returns [] for the default universe
"""

from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from universe import STARTER_UNIVERSE, SECTOR_MAP, NAME_MAP, validate_universe


class TestNoDuplicates:
    def test_no_duplicate_tickers(self):
        symbols = [e["symbol"] for e in STARTER_UNIVERSE]
        assert len(set(symbols)) == len(symbols), (
            f"Duplicate tickers found: "
            f"{[s for s in symbols if symbols.count(s) > 1]}"
        )


class TestTickerValidity:
    def test_no_empty_ticker_strings(self):
        for entry in STARTER_UNIVERSE:
            sym = entry.get("symbol", "")
            assert isinstance(sym, str) and sym.strip(), (
                f"Empty or invalid ticker in entry: {entry}"
            )

    def test_no_whitespace_only_tickers(self):
        for entry in STARTER_UNIVERSE:
            assert entry["symbol"] == entry["symbol"].strip(), (
                f"Ticker has leading/trailing whitespace: {repr(entry['symbol'])}"
            )


class TestSectorLabels:
    def test_no_blank_sector_labels(self):
        for entry in STARTER_UNIVERSE:
            sector = entry.get("sector", "")
            assert isinstance(sector, str) and sector.strip(), (
                f"Blank sector in entry: {entry}"
            )

    def test_all_entries_have_name(self):
        for entry in STARTER_UNIVERSE:
            name = entry.get("name", "")
            assert isinstance(name, str) and name.strip(), (
                f"Blank name in entry: {entry}"
            )


class TestSectorClassification:
    def test_ma_in_financials(self):
        assert SECTOR_MAP.get("MA") == "Financials", (
            f"MA should be in Financials, got: {SECTOR_MAP.get('MA')}"
        )

    def test_v_in_financials(self):
        assert SECTOR_MAP.get("V") == "Financials", (
            f"V should be in Financials, got: {SECTOR_MAP.get('V')}"
        )

    def test_ma_not_in_information_technology(self):
        assert SECTOR_MAP.get("MA") != "Information Technology", (
            "MA must NOT be classified as Information Technology"
        )

    def test_v_not_in_information_technology(self):
        assert SECTOR_MAP.get("V") != "Information Technology", (
            "V must NOT be classified as Information Technology"
        )

    def test_aapl_in_information_technology(self):
        assert SECTOR_MAP.get("AAPL") == "Information Technology"

    def test_jpm_in_financials(self):
        assert SECTOR_MAP.get("JPM") == "Financials"

    def test_jnj_in_health_care(self):
        assert SECTOR_MAP.get("JNJ") == "Health Care"

    def test_xom_in_energy(self):
        assert SECTOR_MAP.get("XOM") == "Energy"


class TestUniverseSize:
    def test_universe_size_approximately_100(self):
        n = len(STARTER_UNIVERSE)
        assert 95 <= n <= 105, (
            f"Expected ~100 stocks, got {n}"
        )

    def test_universe_has_exactly_100_stocks(self):
        assert len(STARTER_UNIVERSE) == 100


class TestSectorDiversity:
    def test_at_least_8_sectors_represented(self):
        sectors = {e["sector"] for e in STARTER_UNIVERSE}
        assert len(sectors) >= 8, (
            f"Expected 8+ sectors, got {len(sectors)}: {sorted(sectors)}"
        )

    def test_all_expected_sectors_present(self):
        expected = {
            "Information Technology",
            "Communication Services",
            "Consumer Discretionary",
            "Consumer Staples",
            "Health Care",
            "Financials",
            "Industrials",
            "Energy",
            "Materials",
            "Real Estate",
            "Utilities",
        }
        present = {e["sector"] for e in STARTER_UNIVERSE}
        missing = expected - present
        assert not missing, f"Missing sectors: {missing}"


class TestLookupMaps:
    def test_sector_map_covers_all_tickers(self):
        for entry in STARTER_UNIVERSE:
            sym = entry["symbol"]
            assert sym in SECTOR_MAP, f"{sym} missing from SECTOR_MAP"
            assert SECTOR_MAP[sym] == entry["sector"]

    def test_name_map_covers_all_tickers(self):
        for entry in STARTER_UNIVERSE:
            sym = entry["symbol"]
            assert sym in NAME_MAP, f"{sym} missing from NAME_MAP"
            assert NAME_MAP[sym] == entry["name"]


class TestValidateUniverseFunction:
    def test_validate_universe_returns_empty_list_for_default(self):
        errors = validate_universe()
        assert errors == [], f"validate_universe() reported errors: {errors}"

    def test_validate_detects_duplicate(self):
        duped = [
            {"symbol": "AAPL", "name": "Apple", "sector": "Information Technology"},
            {"symbol": "AAPL", "name": "Apple Dupe", "sector": "Information Technology"},
        ]
        errors = validate_universe(duped)
        assert any("Duplicate" in e for e in errors)

    def test_validate_detects_empty_symbol(self):
        bad = [{"symbol": "", "name": "Bad", "sector": "Technology"}]
        errors = validate_universe(bad)
        assert any("empty" in e.lower() or "invalid" in e.lower() for e in errors)

    def test_validate_detects_blank_sector(self):
        bad = [{"symbol": "TST", "name": "Test", "sector": ""}]
        errors = validate_universe(bad)
        assert any("sector" in e.lower() for e in errors)

    def test_validate_detects_missing_key(self):
        bad = [{"symbol": "TST", "name": "Test"}]  # missing 'sector'
        errors = validate_universe(bad)
        assert any("sector" in e for e in errors)
