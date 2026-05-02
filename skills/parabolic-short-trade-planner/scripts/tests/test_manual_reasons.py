"""Tests for manual_reasons.build_manual_reasons + flag helpers."""

from manual_reasons import (
    build_manual_reasons,
    requires_manual_confirmation,
    trade_allowed_without_manual,
)

ETB_INVENTORY = {
    "can_open_new_short": True,
    "borrow_fee_manual_check_required": False,
    "manual_locate_required": True,
}
HTB_INVENTORY = {
    "can_open_new_short": False,
    "borrow_fee_manual_check_required": True,
    "manual_locate_required": True,
}
NO_SSR = {"ssr_triggered_today": False, "ssr_carryover_from_prior_day": False}
PM_OK = {"premarket_high": 80.0, "premarket_low": 70.0}
PM_NULL = {"premarket_high": None, "premarket_low": None}


class TestBlockingVsAdvisory:
    def test_etb_clean_only_advisory_locate(self):
        out = build_manual_reasons(ETB_INVENTORY, NO_SSR, [], [], PM_OK)
        assert out["blocking"] == []
        assert "manual_locate_required" in out["advisory"]
        assert trade_allowed_without_manual(out) is True

    def test_htb_blocks(self):
        out = build_manual_reasons(HTB_INVENTORY, NO_SSR, [], [], PM_OK)
        assert "borrow_inventory_unavailable" in out["blocking"]
        assert "htb_borrow_fee_unknown" in out["blocking"]
        assert trade_allowed_without_manual(out) is False

    def test_state_cap_still_in_markup_blocks(self):
        out = build_manual_reasons(ETB_INVENTORY, NO_SSR, ["still_in_markup"], [], PM_OK)
        assert "state_cap:still_in_markup" in out["blocking"]
        assert trade_allowed_without_manual(out) is False

    def test_warning_too_early_advisory_only(self):
        out = build_manual_reasons(ETB_INVENTORY, NO_SSR, [], ["too_early_to_short"], PM_OK)
        assert "warning:too_early_to_short" in out["advisory"]
        assert trade_allowed_without_manual(out) is True

    def test_premarket_null_blocks(self):
        out = build_manual_reasons(ETB_INVENTORY, NO_SSR, [], [], PM_NULL)
        assert "premarket_high_low_unavailable" in out["blocking"]


class TestSSR:
    def test_ssr_active_today_blocks(self):
        ssr = {"ssr_triggered_today": True, "ssr_carryover_from_prior_day": False}
        out = build_manual_reasons(ETB_INVENTORY, ssr, [], [], PM_OK)
        assert "ssr_active_today" in out["blocking"]


class TestFlags:
    def test_requires_manual_when_only_advisory(self):
        out = build_manual_reasons(ETB_INVENTORY, NO_SSR, [], [], PM_OK)
        assert requires_manual_confirmation(out) is True

    def test_no_reasons_does_not_require_manual(self):
        # Pretend a frictionless setup (manual_locate_required off)
        custom = dict(ETB_INVENTORY, manual_locate_required=False)
        out = build_manual_reasons(custom, NO_SSR, [], [], PM_OK)
        assert requires_manual_confirmation(out) is False
        assert trade_allowed_without_manual(out) is True
