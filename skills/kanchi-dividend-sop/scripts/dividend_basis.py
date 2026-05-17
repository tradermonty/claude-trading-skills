"""WS-1: dividend-basis engine (regular / special / variable / freeze / cut).

Pure, dependency-free, offline-testable. Replaces the old
``annual_dividend = profile.lastDiv`` shortcut in build_entry_signals.py,
which fed a trailing/TTM figure that (a) lagged the latest declared raise
(defect D5: CFR FAIL'd at 2.97% though latest declared = 3.06%) and
(b) silently included special/variable dividends (D4: ORI/CALM traps).

Detection ORDER is fixed by improvement-plan v2.1 R-1 — specials MUST be
removed before the variable-policy CoV is computed, otherwise a special
dividend (ORI) inflates the residual stream's variance and the issuer is
misclassified as a CALM-style variable payer.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime

from thresholds import (
    DIVIDEND_EQUALITY_EPS,
    FLOOR_FRESHNESS_BAND_PP,
    FREEZE_GRACE_DAYS,
    MIN_REGULAR_PAYS,
    SPECIAL_EXTREME_MULTIPLE,
    SPECIAL_OUTLIER_MULTIPLE,
    SPECIAL_REVERT_MULTIPLE,
    VARIABLE_POLICY_COV,
)

_SPECIAL_KEYWORDS = ("special", "supplemental", "one-time", "one time", "extra")
_MAINTAIN_KEYWORDS = ("maintain", "unchanged", "same annualized", "no change", "flat")

# 4th-review point 10: a generic "% of net income" appears in ordinary bank /
# insurer payout-ratio language and must NOT alone flag a variable policy.
# Only the strong tier (an explicit variable/earnings-linked policy) flips the
# flag; the weak tier just leaves an audit note.
_STRONG_VARIABLE_KEYWORDS = (
    "variable dividend policy",
    "variable dividend",
    "one-third of net income",
    "1/3 of net income",
    "distribution based on earnings",
    "dividend equal to",
)
_WEAK_PAYOUT_KEYWORDS = (
    "target payout ratio",
    "capital return framework",
    "dividend payout ratio",
    "% of net income",
    "percent of net income",
)

_CADENCE_BY_GAP_DAYS = (
    (45, "monthly", 12),
    (135, "quarterly", 4),
    (240, "semiannual", 2),
    (450, "annual", 1),
)


def _parse_date(value: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


@dataclass
class DividendBasis:
    status: str  # "OK" | "ASSUMPTION-REQUIRED" | "NO-DIVIDEND"
    reasons: list[str] = field(default_factory=list)
    cadence: str = "irregular"
    pays_per_year: int | None = None
    latest_declared_dividend: float | None = None
    latest_declared_annualized: float | None = None
    regular_annual_dividend: float | None = None
    ttm_dividend_incl_special: float | None = None
    special_dividend_flag: bool = False
    variable_policy_flag: bool = False
    cut_flag: bool = False
    freeze_flag: bool = False
    suspension_flag: bool = False
    latest_declared_confirmed: bool = False
    last_increase_date: str | None = None
    dividend_dates_used: list[str] = field(default_factory=list)
    regular_forward_yield_pct: float | None = None
    ttm_yield_pct: float | None = None
    floor_borderline: bool = False


def _infer_cadence(sorted_dates: list[date]) -> tuple[str, int | None]:
    if len(sorted_dates) < 2:
        return "irregular", None
    gaps = [
        (sorted_dates[i + 1] - sorted_dates[i]).days
        for i in range(len(sorted_dates) - 1)
        if (sorted_dates[i + 1] - sorted_dates[i]).days > 0
    ]
    if not gaps:
        return "irregular", None
    median_gap = statistics.median(gaps)
    for max_gap, name, ppy in _CADENCE_BY_GAP_DAYS:
        if median_gap <= max_gap:
            # High dispersion vs the cadence => irregular schedule.
            if len(gaps) >= 3 and statistics.pstdev(gaps) > median_gap * 0.6:
                return "irregular", ppy
            return name, ppy
    return "irregular", 1


def _is_explicit_special(label: object) -> bool:
    if not isinstance(label, str):
        return False
    low = label.lower()
    return any(k in low for k in _SPECIAL_KEYWORDS)


def _sum_window(pays: list[tuple[date, float]], end: date, start_days: int, end_days: int) -> float:
    """Sum amounts with (end - start_days) <= d < (end - end_days) days old."""
    total = 0.0
    for d, amt in pays:
        age = (end - d).days
        if end_days <= age < start_days:
            total += amt
    return total


def analyze_dividends(
    history: list[dict],
    price: float | None,
    *,
    issuer_language: str | None = None,
    floor_pct: float | None = None,
    as_of_date: str | None = None,
) -> DividendBasis:
    """Analyze a stock_dividend `historical` list into a DividendBasis.

    `history` items: {"date": "YYYY-MM-DD", "dividend": float, "label": str?}.
    """
    rows: list[tuple[date, float, object]] = []
    declared: dict[date, bool] = {}
    for item in history or []:
        d = _parse_date(str(item.get("date", "")))
        amt = item.get("dividend")
        try:
            amt = float(amt)
        except (TypeError, ValueError):
            amt = None
        if d is None or amt is None or amt <= 0:
            continue
        rows.append((d, amt, item.get("label")))
        # A non-empty declarationDate means the board formally declared
        # this dividend -> authoritative confirmation for the Data
        # Freshness Gate (5th-review #4 confirmed-source path).
        decl = item.get("declarationDate")
        declared[d] = bool(decl and str(decl).strip())

    if not rows:
        return DividendBasis(status="NO-DIVIDEND", reasons=["no_dividend_history"])

    rows.sort(key=lambda r: r[0])
    all_dates = [r[0] for r in rows]
    cadence, ppy = _infer_cadence(all_dates)

    # --- Step 2: explicit special labels/language ---
    explicit_special = {i for i, r in enumerate(rows) if _is_explicit_special(r[2])}

    # --- Step 3: amount-outliers vs the TRAILING-local median of prior
    #     regular pays (v2.1 R-1). A global median over a 10y+ history is
    #     dragged down by old small dividends, so ordinary long-term
    #     dividend growth would be misclassified as a special and
    #     latest_declared would collapse to a stale amount (D4 recurrence).
    #     Compare each pay only against its recent prior regular pays.
    outlier_special: set[int] = set()
    _TRAILING = max(ppy or 4, 8)
    for i, r in enumerate(rows):
        if i in explicit_special:
            continue
        prior_regular = [
            rows[j][1]
            for j in range(max(0, i - _TRAILING), i)
            if j not in explicit_special and j not in outlier_special
        ]
        if len(prior_regular) < MIN_REGULAR_PAYS:
            # Too little local history to call an outlier -> treat as
            # regular (conservative; avoids flagging early history).
            continue
        local_med = statistics.median(prior_regular)
        if local_med <= 0:
            continue
        if r[1] > SPECIAL_EXTREME_MULTIPLE * local_med:
            outlier_special.add(i)  # extreme isolated spike (magnitude)
        elif r[1] > SPECIAL_OUTLIER_MULTIPLE * local_med:
            # One-off only if a later pay reverts toward the local median;
            # ordinary steep growth keeps rising and is NOT a special.
            revert = any(
                rows[k][1] <= SPECIAL_REVERT_MULTIPLE * local_med
                for k in range(i + 1, min(len(rows), i + 3))
                if k not in explicit_special
            )
            if revert:
                outlier_special.add(i)

    special_idx = explicit_special | outlier_special
    special_flag = bool(special_idx)

    # --- Step 4: residual = regular stream ---
    regular = [(r[0], r[1]) for i, r in enumerate(rows) if i not in special_idx]
    all_pays = [(r[0], r[1]) for r in rows]

    reasons: list[str] = []
    if special_flag:
        reasons.append(f"special_dividends_excluded={len(special_idx)}")

    if len(regular) < MIN_REGULAR_PAYS:
        return DividendBasis(
            status="ASSUMPTION-REQUIRED",
            reasons=reasons + [f"insufficient_regular_pays={len(regular)}"],
            cadence=cadence,
            pays_per_year=ppy,
            special_dividend_flag=special_flag,
        )

    latest_date, latest_amt = regular[-1]
    latest_annualized = latest_amt * ppy if ppy else None

    asof = all_dates[-1]
    asof_reg = regular[-1][0]
    regular_ttm = _sum_window(regular, asof, 366, 0)
    incl_special_ttm = _sum_window(all_pays, asof, 366, 0)

    # --- Step 5: variable-policy on the *residual* (post-special) stream ---
    window = [a for _, a in regular[-max(ppy or 4, 8) :]]
    variable_flag = False
    if len(window) >= MIN_REGULAR_PAYS:
        mean = statistics.fmean(window)
        if mean > 0:
            cov = statistics.pstdev(window) / mean
            variable_flag = cov > VARIABLE_POLICY_COV
    if issuer_language:
        low = issuer_language.lower()
        if any(k in low for k in _STRONG_VARIABLE_KEYWORDS):
            variable_flag = True
        elif not variable_flag and any(k in low for k in _WEAK_PAYOUT_KEYWORDS):
            reasons.append("weak_payout_language_only_review_policy")

    # --- last increase date (ascending scan over regular amounts) ---
    last_increase: date | None = None
    for i in range(1, len(regular)):
        if regular[i][1] > regular[i - 1][1] + DIVIDEND_EQUALITY_EPS:
            last_increase = regular[i][0]

    # --- freeze / cut via year-over-year per-pay RATE (frequency-independent,
    #     robust to rolling-window pay-count drift; v2.1 R-2) ---
    eps = DIVIDEND_EQUALITY_EPS
    cut_flag = False
    freeze_flag = False
    cur_rate = regular[-1][1]
    prior_idx = len(regular) - 1 - ppy if ppy else -1
    prior_rate = regular[prior_idx][1] if prior_idx >= 0 else None
    lang_maintains = bool(
        issuer_language and any(k in issuer_language.lower() for k in _MAINTAIN_KEYWORDS)
    )
    if prior_rate is not None:
        if cur_rate < prior_rate - eps:
            cut_flag = True
        elif abs(cur_rate - prior_rate) <= eps:
            cadence_days = {"monthly": 30, "quarterly": 91, "semiannual": 182}.get(cadence, 365)
            days_since_increase = (asof_reg - last_increase).days if last_increase else 10_000
            time_confirms = days_since_increase > cadence_days + FREEZE_GRACE_DAYS
            if time_confirms or lang_maintains:
                freeze_flag = True
            else:
                reasons.append("flat_window_pending_next_raise")
    else:
        reasons.append("no_prior_year_rate")
        if lang_maintains:
            freeze_flag = True

    # --- suspension: an expected regular declaration is overdue (4th-review
    #     point 4). Distinct from cut (rate down) and freeze (rate held). ---
    cadence_days = {"monthly": 30, "quarterly": 91, "semiannual": 182, "annual": 365}.get(
        cadence, 365
    )
    suspension_flag = False
    ref_date = _parse_date(str(as_of_date)) if as_of_date else None
    if ref_date is not None:
        days_since_last_pay = (ref_date - asof_reg).days
        if days_since_last_pay > cadence_days + FREEZE_GRACE_DAYS:
            suspension_flag = True
            reasons.append(f"declaration_overdue_{days_since_last_pay}d")

    fwd_yield = (
        round(latest_annualized / price * 100, 2)
        if latest_annualized is not None and price and price > 0
        else None
    )
    ttm_yield = (
        round(incl_special_ttm / price * 100, 2)
        if price and price > 0 and incl_special_ttm
        else None
    )

    floor_borderline = False
    if floor_pct is not None and fwd_yield is not None:
        if abs(fwd_yield - floor_pct) <= FLOOR_FRESHNESS_BAND_PP:
            floor_borderline = True
            reasons.append(f"floor_borderline_within_{FLOOR_FRESHNESS_BAND_PP}pp")

    return DividendBasis(
        status="OK",
        reasons=reasons,
        cadence=cadence,
        pays_per_year=ppy,
        latest_declared_dividend=round(latest_amt, 4),
        latest_declared_annualized=round(latest_annualized, 4) if latest_annualized else None,
        regular_annual_dividend=round(regular_ttm, 4) if regular_ttm else None,
        ttm_dividend_incl_special=round(incl_special_ttm, 4) if incl_special_ttm else None,
        special_dividend_flag=special_flag,
        variable_policy_flag=variable_flag,
        cut_flag=cut_flag,
        freeze_flag=freeze_flag,
        suspension_flag=suspension_flag,
        latest_declared_confirmed=declared.get(regular[-1][0], False),
        last_increase_date=last_increase.isoformat() if last_increase else None,
        dividend_dates_used=[d.isoformat() for d, _ in regular[-8:]],
        regular_forward_yield_pct=fwd_yield,
        ttm_yield_pct=ttm_yield,
        floor_borderline=floor_borderline,
    )


def step1_decision(
    basis: DividendBasis,
    floor_pct: float,
    *,
    source_confirmed: bool = False,
) -> tuple[str, str]:
    """Map a DividendBasis to a Step-1 verdict per the v2 decision matrix.

    Returns (verdict, reason). Verdicts: FAIL / STEP1-RECHECK / HOLD-REVIEW /
    STEP1-PASS (caller refines STEP1-PASS into the full tier via WS-2/WS-5).
    """
    if basis.status == "NO-DIVIDEND":
        return "FAIL", "no_dividend"
    if basis.status == "ASSUMPTION-REQUIRED":
        return "STEP1-RECHECK", ";".join(basis.reasons) or "assumption_required"
    if basis.suspension_flag:
        return "FAIL", "dividend_suspension_suspected"
    if basis.variable_policy_flag:
        return "FAIL", "variable_dividend_policy"
    if basis.cut_flag:
        return "FAIL", "dividend_cut"

    fwd = basis.regular_forward_yield_pct
    if fwd is None:
        return "STEP1-RECHECK", "regular_yield_unavailable"

    if fwd < floor_pct:
        # Data Freshness Gate: near-floor + unconfirmed source -> recheck,
        # never a hard FAIL (defect D5).
        if basis.floor_borderline and not source_confirmed:
            return "STEP1-RECHECK", "floor_borderline_unconfirmed_dividend"
        return "FAIL", f"regular_yield_{fwd}_below_floor_{floor_pct}"

    # At/above floor on regular yield.
    if basis.floor_borderline and not source_confirmed:
        return "STEP1-RECHECK", "floor_borderline_confirm_latest_declared"
    if basis.freeze_flag:
        return "HOLD-REVIEW", "dividend_freeze"
    return "STEP1-PASS", "regular_yield_above_floor"
