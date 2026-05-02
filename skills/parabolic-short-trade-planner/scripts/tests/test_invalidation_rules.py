"""Tests for invalidation_rules.check_invalidation."""

import pytest
from invalidation_rules import check_invalidation


def _ok(**overrides) -> dict:
    base = {
        "ticker": "XYZ",
        "close": 50.0,
        "market_cap_usd": 5_000_000_000,
        "adv_20d_usd": 100_000_000,
        "days_listed": 365,
        "earnings_within_days": None,
        "catalyst_blackout": False,
    }
    base.update(overrides)
    return base


class TestEarnings:
    def test_within_blackout_invalid(self):
        out = check_invalidation(_ok(earnings_within_days=1))
        assert out["is_invalid"] is True
        assert any("earnings" in r for r in out["reasons"])

    def test_outside_blackout_ok(self):
        out = check_invalidation(_ok(earnings_within_days=5))
        assert out["is_invalid"] is False


class TestSafeLargecapVsClassicQm:
    def test_safelargecap_rejects_smallcap(self):
        out = check_invalidation(_ok(market_cap_usd=500_000_000), mode="safe_largecap")
        assert out["is_invalid"] is True
        assert any("market_cap" in r for r in out["reasons"])

    def test_classic_qm_keeps_smallcap_above_300m(self):
        out = check_invalidation(_ok(market_cap_usd=500_000_000), mode="classic_qm")
        assert out["is_invalid"] is False

    def test_classic_qm_rejects_microcap(self):
        out = check_invalidation(_ok(market_cap_usd=200_000_000), mode="classic_qm")
        assert out["is_invalid"] is True


class TestADVAndPrice:
    def test_low_adv_rejected(self):
        out = check_invalidation(_ok(adv_20d_usd=10_000_000), mode="safe_largecap")
        assert any("adv" in r for r in out["reasons"])

    def test_low_price_rejected(self):
        out = check_invalidation(_ok(close=4.50))
        assert any("price" in r for r in out["reasons"])


class TestRecentIPO:
    def test_recently_listed_rejected(self):
        out = check_invalidation(_ok(days_listed=30))
        assert any("listed" in r for r in out["reasons"])


class TestUnknownMode:
    def test_raises(self):
        with pytest.raises(ValueError):
            check_invalidation(_ok(), mode="bogus")


class TestMultipleReasons:
    def test_collects_all(self):
        bad = _ok(
            close=2.0,
            market_cap_usd=100_000_000,
            adv_20d_usd=500_000,
            days_listed=10,
            earnings_within_days=1,
        )
        out = check_invalidation(bad, mode="safe_largecap")
        assert out["is_invalid"] is True
        assert len(out["reasons"]) >= 4  # earnings + market_cap + adv + price + listed
