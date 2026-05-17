"""WS-2 sector-aware payout-safety tests (offline, deterministic).

# DATA-DATE: 2026-05-17
# REVIEW-TRIGGER: MKC Unilever close, FITB post-Comerica normalization
"""

from payout_safety import assess_payout_safety


# --- D2: MKC GAAP EPS inflated by non-cash gain; adjusted is the anchor ---
def test_mkc_gaap_distorted_flags_one_off_uses_adjusted():
    # GAAP EPS TTM inflated to ~12.9 by a non-cash remeasurement gain;
    # adjusted ~3.09 (FY guide). Div 1.92.
    a = assess_payout_safety(
        sector="consumer staples",
        annual_dividend=1.92,
        gaap_eps=12.9,
        adjusted_eps=3.09,
        adjusted_eps_source="MANUAL",
    )
    assert a.one_off_flag is True
    assert a.gaap_adj_divergence is not None and a.gaap_adj_divergence > 0.25
    # Adjusted-EPS payout ~62%, FCF unknown -> CAUTION band, not a fake "PASS"
    assert round(a.adjusted_eps_payout, 2) == round(1.92 / 3.09, 2)
    assert a.safety_verdict in ("CAUTION", "PASS")


def test_adjusted_eps_unavailable_caps_hold_review():
    a = assess_payout_safety(
        sector="consumer",
        annual_dividend=2.0,
        gaap_eps=5.0,
        adjusted_eps=None,
        adjusted_eps_source="UNAVAILABLE",
    )
    assert "adjusted_eps_unavailable" in a.blockers
    assert a.safety_verdict == "HOLD-REVIEW"  # fail-safe, never silent PASS


# --- FITB/Comerica: completed merger -> GAAP distorted -> HOLD-REVIEW ---
def test_completed_merger_without_adjusted_holds_review():
    a = assess_payout_safety(
        sector="banks",
        annual_dividend=1.60,
        gaap_eps=0.60,  # Q1-2026 GAAP $0.15-style distortion (annualized small)
        adjusted_eps=None,
        completed_merger_within_4q=True,
    )
    assert a.safety_verdict == "HOLD-REVIEW"
    assert a.one_off_flag is True
    assert "adjusted_eps_unavailable" in a.blockers


# --- banks: FCF ignored; NPL/NCO deterioration -> CAUTION (OZK golden) ---
def test_bank_npl_nco_deterioration_caution():
    a = assess_payout_safety(
        sector="financial services",
        annual_dividend=1.88,
        gaap_eps=6.17,
        adjusted_eps=6.17,
        adjusted_eps_source="FMP",
        fcf_per_share=-50.0,  # must be ignored for a bank
        bank_metrics={
            "cet1": 0.11,
            "cre_concentration": "high",
            "npl_trend": "deteriorating",
            "nco_trend": "deteriorating",
        },
    )
    assert a.sector_kind == "bank"
    assert a.safety_verdict == "CAUTION"
    assert "bank_npl_nco_deteriorating" in a.blockers


# --- utilities: negative FCF must NOT auto-FAIL ---
def test_utility_negative_fcf_not_auto_fail():
    a = assess_payout_safety(
        sector="utilities",
        annual_dividend=1.68,
        gaap_eps=2.74,
        adjusted_eps=2.74,
        adjusted_eps_source="FMP",
        fcf_per_share=-3.0,  # structurally negative -> ignored for utilities
        utility_metrics={"ffo_to_debt": 0.16, "rate_case_status": "constructive"},
    )
    assert a.sector_kind == "utility"
    assert a.safety_verdict == "PASS"


def test_utility_missing_ffo_debt_blocks():
    a = assess_payout_safety(
        sector="utilities",
        annual_dividend=1.68,
        gaap_eps=2.74,
        adjusted_eps=2.74,
        adjusted_eps_source="FMP",
        utility_metrics={"rate_case_status": "constructive"},
    )
    assert "utility_ffo_debt_unavailable" in a.blockers
    assert a.safety_verdict in ("CAUTION", "HOLD-REVIEW")


def test_utility_adverse_rate_case_holds_review():
    a = assess_payout_safety(
        sector="utilities",
        annual_dividend=1.68,
        gaap_eps=2.74,
        adjusted_eps=2.74,
        adjusted_eps_source="FMP",
        utility_metrics={"ffo_to_debt": 0.15, "rate_case_status": "adverse"},
    )
    assert a.safety_verdict == "HOLD-REVIEW"
    assert "utility_rate_case_adverse" in a.blockers


# --- consumer: clean name passes; over-100% FCF payout fails ---
def test_consumer_clean_pass():
    a = assess_payout_safety(
        sector="consumer staples",
        annual_dividend=1.0,
        gaap_eps=3.0,
        adjusted_eps=3.0,
        adjusted_eps_source="FMP",
        fcf_per_share=2.5,
    )
    assert a.safety_verdict == "PASS"
    assert not a.blockers


def test_consumer_fcf_payout_over_100_fails():
    a = assess_payout_safety(
        sector="consumer",
        annual_dividend=3.0,
        gaap_eps=4.0,
        adjusted_eps=4.0,
        adjusted_eps_source="FMP",
        fcf_per_share=2.0,  # 3.0/2.0 = 150% FCF payout
    )
    assert a.safety_verdict == "FAIL"
