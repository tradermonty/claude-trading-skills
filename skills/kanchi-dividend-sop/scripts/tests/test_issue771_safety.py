"""Issue #771: payout-safety routing ignores industry (offline, deterministic).

FMP reports insurers and REITs under broad sectors, so the sector-only
dispatch assessed an insurer on bank rules and a REIT on the consumer
triad. Routing must consult FMP `industry` (and accept an explicit kind
override), record the routing source, and HOLD-REVIEW on an unknown /
ambiguous classification instead of silently applying another sector's
rules.
"""

from datetime import date, timedelta

from build_entry_signals import FMPClient, build_entry_row
from event_scanner import CLEAN_CONFIRMED, ScanResult
from payout_safety import assess_payout_safety

_CLEAN = ScanResult(ticker="_", result=CLEAN_CONFIRMED)


def _q(start, n, amt, step=91):
    amounts = amt if isinstance(amt, list) else [amt] * n
    return [
        {
            "date": (start + timedelta(days=step * i)).isoformat(),
            "dividend": amounts[i],
            "label": "cash",
        }
        for i in range(n)
    ]


# --- Issue repro: ORI is an insurer, not a bank ---
def test_ori_insurer_routed_by_industry_not_sector():
    a = assess_payout_safety(
        sector="Financial Services",
        industry="Insurance - Property & Casualty",
        annual_dividend=1.26,
        gaap_eps=3.0,
    )
    assert a.sector_kind == "insurer"
    assert a.sector_kind_source == "industry"
    assert "bank_capital_unavailable" not in a.blockers
    assert "bank_cre_concentration_unavailable" not in a.blockers


def test_bank_industry_routes_to_bank():
    a = assess_payout_safety(
        sector="Financial Services",
        industry="Banks - Regional",
        annual_dividend=1.88,
        gaap_eps=6.17,
        adjusted_eps=6.17,
        adjusted_eps_source="FMP",
        bank_metrics={"cet1": 0.11, "cre_concentration": "low"},
    )
    assert a.sector_kind == "bank"
    assert a.sector_kind_source == "industry"
    assert a.safety_verdict == "PASS"


def test_unambiguous_bank_sector_fallback():
    # An explicit bank sector needs no finer industry; broad financial sectors do.
    a = assess_payout_safety(
        sector="Banks",
        annual_dividend=1.88,
        gaap_eps=6.17,
        adjusted_eps=6.17,
        adjusted_eps_source="FMP",
        bank_metrics={"cet1": 0.11, "cre_concentration": "low"},
    )
    assert a.sector_kind == "bank"
    assert a.sector_kind_source == "sector"


def test_industry_beats_sector_on_conflict():
    # Industry is finer than sector: a regulated-electric name must not
    # take the bank path even if the sector says Financial Services.
    a = assess_payout_safety(
        sector="Financial Services",
        industry="Utilities - Regulated Electric",
        annual_dividend=1.5,
        gaap_eps=2.5,
        adjusted_eps=2.5,
        adjusted_eps_source="FMP",
        utility_metrics={"ffo_to_debt": 0.18, "rate_case_status": "constructive"},
    )
    assert a.sector_kind == "utility"
    assert a.sector_kind_source == "industry"


# --- REIT: AFFO is the anchor, not GAAP/FCF ---
def test_reit_routed_by_industry_with_affo():
    a = assess_payout_safety(
        sector="Real Estate",
        industry="REIT - Residential",
        annual_dividend=1.26,
        gaap_eps=0.8,  # GAAP EPS is depreciation-distorted for REITs
        fcf_per_share=-1.0,  # FCF is meaningless for REITs: must be ignored
        reit_metrics={"affo_per_share": 2.0},
    )
    assert a.sector_kind == "reit"
    assert a.sector_kind_source == "industry"
    assert a.safety_verdict == "PASS"


def test_reit_affo_unavailable_blocks_caution():
    a = assess_payout_safety(
        sector="Real Estate",
        industry="REIT - Retail",
        annual_dividend=1.26,
        gaap_eps=0.8,
    )
    assert a.sector_kind == "reit"
    assert "reit_affo_per_share_unavailable" in a.blockers
    assert a.safety_verdict == "CAUTION"


def test_reit_affo_payout_over_100_fails():
    a = assess_payout_safety(
        sector="Real Estate",
        industry="REIT - Diversified",
        annual_dividend=1.26,
        gaap_eps=0.8,
        reit_metrics={"affo_per_share": 1.0},  # 126% AFFO payout
    )
    assert a.safety_verdict == "FAIL"


def test_reit_affo_payout_caution_band():
    a = assess_payout_safety(
        sector="Real Estate",
        industry="REIT - Office",
        annual_dividend=1.26,
        gaap_eps=0.8,
        reit_metrics={"affo_per_share": 1.4},  # 90% AFFO payout
    )
    assert a.safety_verdict == "CAUTION"


def test_non_reit_real_estate_stays_consumer():
    a = assess_payout_safety(
        sector="Real Estate",
        industry="Real Estate - Development",
        annual_dividend=1.0,
        gaap_eps=3.0,
        adjusted_eps=3.0,
        adjusted_eps_source="FMP",
        fcf_per_share=2.5,
    )
    assert a.sector_kind == "consumer"
    assert a.sector_kind_source == "industry"
    assert a.safety_verdict == "PASS"


# --- Unknown / ambiguous: HOLD-REVIEW, never a silent other-sector rule ---
def test_unknown_sector_and_industry_holds_review():
    a = assess_payout_safety(sector=None, annual_dividend=1.0, gaap_eps=4.0)
    assert a.sector_kind == "unknown"
    assert a.sector_kind_source == "unknown"
    assert "sector_kind_unknown" in a.blockers
    assert a.safety_verdict == "HOLD-REVIEW"


def test_unknown_sector_string_holds_review():
    a = assess_payout_safety(sector="Conglomerates", annual_dividend=1.0, gaap_eps=4.0)
    assert a.sector_kind == "unknown"
    assert a.safety_verdict == "HOLD-REVIEW"


def test_unrecognized_industry_falls_back_to_sector():
    a = assess_payout_safety(
        sector="Healthcare",
        industry="Biotechnology",
        annual_dividend=1.0,
        gaap_eps=3.0,
        adjusted_eps=3.0,
        adjusted_eps_source="FMP",
        fcf_per_share=2.5,
    )
    assert a.sector_kind == "consumer"
    assert a.sector_kind_source == "sector"


def test_explicit_kind_override_wins():
    a = assess_payout_safety(
        sector="Financial Services",
        industry="Insurance - Property & Casualty",
        sector_kind_override="bank",
        annual_dividend=1.88,
        gaap_eps=6.17,
        adjusted_eps=6.17,
        adjusted_eps_source="FMP",
        bank_metrics={"cet1": 0.11, "cre_concentration": "low"},
    )
    assert a.sector_kind == "bank"
    assert a.sector_kind_source == "override"


def test_invalid_override_holds_review():
    a = assess_payout_safety(
        sector="Financial Services",
        sector_kind_override="mystery",
        annual_dividend=1.0,
        gaap_eps=4.0,
    )
    assert a.sector_kind == "unknown"
    assert a.safety_verdict == "HOLD-REVIEW"


# --- Plumbing: industry flows profile -> financials -> assessment ---
def test_get_financials_carries_industry(monkeypatch):
    client = FMPClient(api_key="test")

    def fake_get(endpoint, params):
        if endpoint == "income-statement":
            return [{"epsDiluted": 3.0, "weightedAverageShsOutDil": 100}]
        if endpoint == "cash-flow-statement":
            return [{"freeCashFlow": 250.0}]
        return []

    monkeypatch.setattr(client, "_get", fake_get)
    fin = client.get_financials(
        "ORI",
        sector="Financial Services",
        industry="Insurance - Property & Casualty",
    )
    assert fin["industry"] == "Insurance - Property & Casualty"
    assert fin["sector"] == "Financial Services"


# --- End-to-end: routing decision recorded on the entry row ---
def test_entry_row_records_industry_routing():
    hist = _q(date(2023, 1, 1), 13, [0.30] * 13)
    row = build_entry_row(
        ticker="ORI",
        alpha_pp=0.5,
        quote={"price": 37.0},
        profile={
            "sector": "Financial Services",
            "industry": "Insurance - Property & Casualty",
        },
        key_metrics=[{"dividendYield": 0.032}],
        dividend_history=hist,
        floor_pct=3.0,
        financials={
            "sector": "Financial Services",
            "industry": "Insurance - Property & Casualty",
            "gaap_eps": 3.0,
            "adjusted_eps": 3.0,
            "adjusted_eps_source": "FMP",
            "insurer_metrics": {
                "combined_ratio": 0.95,
                "reserve_development": "favorable",
                "statutory_capital": "strong",
            },
        },
        event_scan=_CLEAN,
    )
    assert row["payout_safety"]["sector_kind"] == "insurer"
    assert row["payout_safety"]["sector_kind_source"] == "industry"
    assert "bank_capital_unavailable" not in row["pre_order_blockers"]


def test_broad_financial_and_real_estate_sectors_cannot_select_unproven_modules():
    for sector, industry in (
        ("Financial Services", "Asset Management"),
        ("Financial Services", "Financial - Credit Services"),
        ("Financial Services", None),
        ("Financials", None),
        ("Real Estate", None),
        ("Real Estate", "Unrecognized property business"),
    ):
        a = assess_payout_safety(
            sector=sector,
            industry=industry,
            annual_dividend=1.0,
            gaap_eps=4.0,
            adjusted_eps=4.0,
            adjusted_eps_source="MANUAL",
            fcf_per_share=5.0,
            bank_metrics={"cet1": 0.12, "cre_concentration": "low"},
        )
        assert a.sector_kind == "unknown", (sector, industry, a)
        assert a.safety_verdict == "HOLD-REVIEW"
        assert "sector_kind_unknown" in a.blockers
