#!/usr/bin/env python3
"""Build Kanchi Step 5 entry signals using live FMP data."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from dividend_basis import _parse_date, _positive_amount, analyze_dividends, step1_decision
from event_scanner import ScanResult, apply_event_cap
from fmp_client import FMPClient as SharedFMPClient
from payout_safety import assess_payout_safety
from regular_yield_history import (
    RegularYieldHistory,
    YieldHistoryInputError,
    apply_frequency_special_label,
    fetch_window_start,
    latest_dividend_unconfirmed,
    load_yield_history,
    reconstruct_regular_yield,
)
from sourced_financials import FinancialsInputError, load_financials, merge_financials
from thresholds import SCHEMA_VERSION, VERDICTS
from verdict import build_run_context, synthesize_verdict


def parse_ticker_csv(raw: str) -> list[str]:
    tickers: list[str] = []
    for part in raw.split(","):
        value = part.strip().upper()
        if not value:
            continue
        if value not in tickers:
            tickers.append(value)
    return tickers


def load_tickers(input_path: Path | None, tickers_csv: str | None) -> list[str]:
    if tickers_csv:
        return parse_ticker_csv(tickers_csv)

    if not input_path:
        return []

    payload = json.loads(input_path.read_text())
    tickers: list[str] = []

    def append_ticker(value: Any) -> None:
        ticker = str(value or "").strip().upper()
        if ticker and ticker not in tickers:
            tickers.append(ticker)

    raw_candidates = payload.get("candidates")
    if isinstance(raw_candidates, list):
        for item in raw_candidates:
            if isinstance(item, dict):
                append_ticker(item.get("ticker") or item.get("symbol"))
            else:
                append_ticker(item)

    # value-dividend-screener and dividend-growth-pullback-screener both
    # publish their ranked JSON rows as ``stocks[].symbol``. Accept that
    # contract directly so workflow handoff does not depend on a prose-only
    # manual rename to candidates/ticker.
    raw_stocks = payload.get("stocks")
    if isinstance(raw_stocks, list):
        for item in raw_stocks:
            if isinstance(item, dict):
                append_ticker(item.get("symbol") or item.get("ticker"))
            else:
                append_ticker(item)

    raw_tickers = payload.get("tickers")
    if isinstance(raw_tickers, list):
        for item in raw_tickers:
            append_ticker(item)

    return tickers


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _quote_price_date(quote: dict[str, Any] | None) -> str | None:
    """ISO price date from an FMP quote row (#770).

    FMP /stable/quote carries `timestamp` (Unix epoch seconds). A
    millisecond epoch is divided down; a `date` string is accepted as a
    fallback. Returns None when neither is usable, so a missing date is
    explicit instead of silently defaulting to the run date.
    """
    if not isinstance(quote, dict):
        return None
    ts = to_float(quote.get("timestamp"))
    if ts is not None:
        if ts > 1e12:  # millisecond epoch
            ts /= 1000
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        except (ValueError, OverflowError, OSError):
            return None
    raw = quote.get("date")
    if isinstance(raw, str) and raw.strip():
        try:
            return datetime.strptime(raw.strip(), "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None
    return None


def normalize_metrics_yields(metrics: list[dict[str, Any]], max_points: int = 5) -> list[float]:
    yields_pct: list[float] = []
    for item in metrics:
        raw = to_float(item.get("dividendYield"))
        if raw is None or raw <= 0:
            continue
        # FMP usually returns decimal (0.035). Guard for percent-style values.
        normalized = raw * 100 if raw <= 1.5 else raw
        yields_pct.append(normalized)
        if len(yields_pct) >= max_points:
            break
    return yields_pct


def average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


class FMPClient(SharedFMPClient):
    """Kanchi domain methods backed by the generated shared transport."""

    def __init__(self, api_key: str, sleep_seconds: float = 0.15, timeout: int = 30):
        super().__init__(api_key=api_key)
        self.sleep_seconds = sleep_seconds
        self.RATE_LIMIT_DELAY = sleep_seconds
        self.timeout = timeout

    @property
    def api_calls(self) -> int:
        return self.api_calls_made

    def get_batch_quotes(self, tickers: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch quotes for all tickers (one /stable quote request per symbol).

        Comma-batched /stable quote requests silently return [], so each symbol
        is requested individually.
        """
        result: dict[str, dict[str, Any]] = {}
        for ticker in tickers:
            data = self._get("quote", {"symbol": ticker})
            if not isinstance(data, list) or not data:
                continue
            row = data[0]
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol", "")).strip().upper()
            if symbol:
                result[symbol] = row
        return result

    def get_batch_profiles(self, tickers: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch profiles for all tickers (one /stable profile request per symbol).

        /stable renamed the trailing dividend field lastDiv -> lastDividend; a
        lastDiv alias is restored so downstream consumers are unchanged.
        """
        result: dict[str, dict[str, Any]] = {}
        for ticker in tickers:
            data = self._get("profile", {"symbol": ticker})
            if not isinstance(data, list) or not data:
                continue
            row = data[0]
            if not isinstance(row, dict):
                continue
            if "lastDiv" not in row and "lastDividend" in row:
                row["lastDiv"] = row["lastDividend"]
            symbol = str(row.get("symbol", "")).strip().upper()
            if symbol:
                result[symbol] = row
        return result

    def get_ratios(self, ticker: str, limit: int = 10) -> list[dict[str, Any]]:
        """Annual financial ratios (the 5y dividend-yield history series).

        On /stable, dividendYield and dividendPerShare moved off key-metrics
        onto the ratios endpoint (dividendYield is a decimal, e.g. 0.0404).
        """
        data = self._get("ratios", {"symbol": ticker, "limit": limit})
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        return []

    def get_stock_dividend(self, ticker: str) -> list[dict[str, Any]] | None:
        """WS-1: full declared-dividend history (regular + special).

        /stable dividends returns a flat list (the legacy
        historical-price-full/stock_dividend {symbol, historical:[]} wrapper is
        gone). Return None for failure/malformed evidence; only a confirmed
        empty response is []. Keep raw and adjusted amounts for the basis engine.
        """
        data = self._get("dividends", {"symbol": ticker})
        if isinstance(data, list):
            if any(
                not isinstance(row, dict)
                or _parse_date(str(row.get("date", ""))) is None
                or (
                    _positive_amount(row.get("dividend")) is None
                    and _positive_amount(row.get("adjDividend")) is None
                )
                for row in data
            ):
                return None
            # /stable rows carry `frequency` (e.g. "Special") but no `label`;
            # map Special to the label dividend_basis reads (#834). "Irregular"
            # is not special. Rows are never de-duplicated by date: a regular
            # and a special payment can share an ex-date.
            return [apply_frequency_special_label(row) for row in data]
        return None

    def get_price_history(self, ticker: str, start: str, end: str) -> list[dict[str, Any]]:
        """Daily EOD rows (split-adjusted close) from `start` to `end`; [] on failure."""
        try:
            data = self._request(
                f"{self.STABLE_URL}/historical-price-eod/full",
                {"symbol": ticker, "from": start, "to": end},
            )
        except Exception:  # transport already redacts; never surface raw errors
            return []
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        return []

    def get_splits(self, ticker: str) -> list[dict[str, Any]] | None:
        """Split history rows; None when the request failed (unknown, not 'no splits')."""
        try:
            data = self._request(f"{self.STABLE_URL}/splits", {"symbol": ticker})
        except Exception:
            return None
        if isinstance(data, list) and all(
            isinstance(row, dict) and _parse_date(str(row.get("date", ""))) is not None
            for row in data
        ):
            return [dict(row) for row in data]
        return None

    def get_financials(
        self, ticker: str, sector: str | None = None, industry: str | None = None
    ) -> dict[str, Any]:
        """WS-2 (5th-review F1): minimal financials for the payout triad.

        Adjusted EPS is NOT in FMP -> source UNAVAILABLE by design (the
        consumer path then fail-safes to HOLD-REVIEW; sector paths use
        sector metrics). Sector metric dicts are left None when FMP does
        not expose them, which deterministically raises *_unavailable
        blockers (CAUTION) for manual fill rather than a false PASS.
        """
        inc = self._get("income-statement", {"symbol": ticker, "limit": 1})
        cf = self._get("cash-flow-statement", {"symbol": ticker, "limit": 1})
        gaap_eps = None
        if isinstance(inc, list) and inc:
            # /stable renamed epsdiluted -> epsDiluted; keep both as fallbacks.
            gaap_eps = (
                to_float(inc[0].get("epsDiluted"))
                or to_float(inc[0].get("epsdiluted"))
                or to_float(inc[0].get("eps"))
            )
        fcf_ps = None
        if isinstance(cf, list) and cf:
            fcf = to_float(cf[0].get("freeCashFlow"))
            shares = (
                to_float(inc[0].get("weightedAverageShsOutDil"))
                if (isinstance(inc, list) and inc)
                else None
            )
            if fcf is not None and shares:
                fcf_ps = fcf / shares
        return {
            "sector": sector,
            "industry": industry,
            "gaap_eps": gaap_eps,
            "adjusted_eps": None,
            "adjusted_eps_source": "UNAVAILABLE",
            "fcf_per_share": fcf_ps,
        }


def build_entry_row(
    ticker: str,
    alpha_pp: float,
    quote: dict[str, Any] | None,
    profile: dict[str, Any] | None,
    key_metrics: list[dict[str, Any]],
    dividend_history: list[dict[str, Any]] | None = None,
    floor_pct: float | None = None,
    financials: dict[str, Any] | None = None,
    event_scan: ScanResult | None = None,
    as_of: str | None = None,
    yield_history: RegularYieldHistory | None = None,
    split_history: list[dict[str, Any]] | None = None,
    require_split_evidence: bool = False,
) -> dict[str, Any]:
    price = to_float((quote or {}).get("price"))
    # #770 finding 3: record the date the price is as of, and flag it when it
    # differs from the run's as_of (a stale quote silently skews yields).
    price_date = _quote_price_date(quote)
    price_date_mismatch = bool(price_date and as_of and price_date != as_of)

    # WS-1: prefer the regular run-rate from declared-dividend history over
    # profile.lastDiv (which is a trailing/TTM figure that lagged the latest
    # declared raise -> defect D5 -- and silently bundled specials -> D4).
    basis = analyze_dividends(
        dividend_history,
        price,
        issuer_language=(profile or {}).get("issuer_language"),
        issuer_currency=(profile or {}).get("currency"),
        is_adr=(profile or {}).get("isAdr") is True,
        floor_pct=floor_pct,
        as_of_date=as_of,
        split_history=split_history,
        require_split_evidence=require_split_evidence,
    )

    # An unavailable regular basis cannot be replaced by a profile TTM number.
    annual_dividend = basis.latest_declared_annualized

    yields_5y = normalize_metrics_yields(key_metrics, max_points=5)
    avg_yield_5y_pct_raw = average(yields_5y)
    avg_yield_5y_pct = round(avg_yield_5y_pct_raw, 2) if avg_yield_5y_pct_raw is not None else None

    # Provider annual ratios have no regular/special split or matching price
    # evidence. Absence of a detected special in a partial history is not proof.
    provider_avg_yield = avg_yield_5y_pct
    numerator_basis = (
        "regular_only"
        if (basis is not None and basis.latest_declared_annualized is not None)
        else "unavailable"
    )
    target_withheld_reason = None
    reconstructed = False
    if basis is not None:
        # #834: a validated regular-only reconstruction (monthly closes + dividend
        # rows, specials removed) is the only thing that may replace the withheld
        # average. It never applies when the numerator itself is not regular-only,
        # and provider ratios stay reported as provider_avg_5y_yield_pct only.
        if (
            yield_history is not None
            and yield_history.status == "OK"
            and yield_history.avg_yield_pct is not None
            and numerator_basis == "regular_only"
            and not latest_dividend_unconfirmed(dividend_history or [], as_of)
        ):
            reconstructed = True
            avg_yield_5y_pct = yield_history.avg_yield_pct
        else:
            if (
                yield_history is not None
                and yield_history.status == "OK"
                and numerator_basis == "regular_only"
            ):
                # The history is fine but the CURRENT numerator is an Irregular or
                # not-yet-confirmed outlier payment: it cannot anchor a target.
                target_withheld_reason = "latest_dividend_unconfirmed"
            else:
                target_withheld_reason = (
                    "regular_only_average_unavailable"
                    if numerator_basis == "regular_only"
                    else "regular_dividend_unavailable"
                )
            avg_yield_5y_pct = None

    target_yield_pct = (
        round(avg_yield_5y_pct + alpha_pp, 2) if avg_yield_5y_pct is not None else None
    )
    buy_target_price = None
    if annual_dividend is not None and target_yield_pct is not None and target_yield_pct > 0:
        buy_target_price = round(annual_dividend / (target_yield_pct / 100), 2)

    current_yield_pct = None
    if annual_dividend is not None and price is not None and price > 0:
        current_yield_pct = round((annual_dividend / price) * 100, 2)

    drop_needed_pct = None
    if price is not None and buy_target_price is not None and price > 0:
        drop_needed_pct = round(max(0.0, (price - buy_target_price) / price * 100), 2)

    signal = "ASSUMPTION-REQUIRED"
    if price is not None and buy_target_price is not None:
        signal = "TRIGGERED" if price <= buy_target_price else "WAIT"

    notes: list[str] = []
    if quote is None:
        notes.append("quote_missing")
    if profile is None:
        notes.append("profile_missing")
    if annual_dividend is None:
        notes.append("annual_dividend_missing")
    if provider_avg_yield is None:
        notes.append("avg_5y_yield_missing")
    elif len(yields_5y) < 5:
        notes.append(f"avg_5y_yield_points={len(yields_5y)}")

    if target_withheld_reason:
        notes.append(target_withheld_reason)
        if yield_history is not None:
            for reason in yield_history.reasons:
                notes.append(f"yield_history:{reason}")
    if price_date_mismatch:
        notes.append("price_date_mismatch")

    row: dict[str, Any] = {
        "ticker": ticker,
        "annual_dividend_basis": numerator_basis,
        "historical_yield_basis": (
            "regular_only_reconstructed" if reconstructed else "provider_total_unverified"
        ),
        "yield_basis": (
            "regular_only_reconstructed"
            if reconstructed
            else ("unavailable" if target_withheld_reason else "provider_total_unverified")
        ),
        "target_withheld_reason": target_withheld_reason,
        "provider_avg_5y_yield_pct": provider_avg_yield,
        "signal": signal,
        "price": round(price, 2) if price is not None else None,
        "price_date": price_date,
        "price_date_mismatch": price_date_mismatch,
        "annual_dividend_per_share": round(annual_dividend, 4)
        if annual_dividend is not None
        else None,
        "current_yield_pct": current_yield_pct,
        "avg_5y_yield_pct": avg_yield_5y_pct,
        "alpha_pp": round(alpha_pp, 2),
        "target_yield_pct": target_yield_pct,
        "buy_target_price": buy_target_price,
        "drop_needed_pct": drop_needed_pct,
        "yield_observation_count": (
            yield_history.observation_count
            if reconstructed and yield_history is not None
            else (0 if target_withheld_reason else len(yields_5y))
        ),
        "provider_yield_observation_count": len(yields_5y),
        "notes": notes,
    }

    if yield_history is not None:
        # Audit observations stay out of the row (and the CSV); the summary is enough.
        row["yield_history"] = yield_history.summary()

    # WS-1: attach the dividend-basis breakdown + Step-1 decision.
    if basis is not None:
        row["dividend_basis"] = {
            "status": basis.status,
            "dividend_amount_basis": basis.dividend_amount_basis,
            "cadence": basis.cadence,
            "latest_declared_annualized": basis.latest_declared_annualized,
            "regular_annual_dividend": basis.regular_annual_dividend,
            "ttm_dividend_incl_special": basis.ttm_dividend_incl_special,
            "regular_forward_yield_pct": basis.regular_forward_yield_pct,
            "ttm_yield_pct": basis.ttm_yield_pct,
            "special_dividend_flag": basis.special_dividend_flag,
            "variable_policy_flag": basis.variable_policy_flag,
            "cut_flag": basis.cut_flag,
            "cut_confirmation_required": basis.cut_confirmation_required,
            "cut_amount_basis": basis.cut_amount_basis,
            "original_dividend_currency": basis.original_dividend_currency,
            "freeze_flag": basis.freeze_flag,
            "suspension_flag": basis.suspension_flag,
            "last_increase_date": basis.last_increase_date,
            "dividend_dates_used": basis.dividend_dates_used,
            "floor_borderline": basis.floor_borderline,
            "reasons": basis.reasons,
        }
        if floor_pct is not None:
            verdict, reason = step1_decision(
                basis, floor_pct, source_confirmed=basis.latest_declared_confirmed
            )
            row["step1_verdict"] = verdict
            row["step1_reason"] = reason
        for flag in (
            "special_dividend_flag",
            "variable_policy_flag",
            "cut_flag",
            "freeze_flag",
            "suspension_flag",
        ):
            if getattr(basis, flag):
                notes.append(flag)
        if basis.floor_borderline:
            notes.append("floor_borderline")

    pre_order_blockers: list[str] = []
    if basis is not None and basis.cut_confirmation_required:
        pre_order_blockers.append("dividend_cut_currency_basis_unconfirmed")
    if target_withheld_reason:
        pre_order_blockers.append(target_withheld_reason)
    if basis is not None:
        # freeze_flag is intentionally NOT a blocker here: its disposition
        # (CONDITIONAL-PASS vs HOLD-REVIEW) is decided by synthesize_verdict
        # from step1_verdict + safety. cut/variable/suspension already force
        # step1 FAIL; listing them keeps the audit trail explicit.
        for flag in ("variable_policy_flag", "cut_flag", "suspension_flag"):
            if getattr(basis, flag):
                pre_order_blockers.append(flag)
        if basis.floor_borderline:
            pre_order_blockers.append("dividend_source_stale")

    # WS-3 FIRST (6th-review High2/High3): a missing scan is SKIPPED, never
    # silently clean; the pessimistic cap must run on every row, and a
    # completed merger must reach WS-2 *before* payout safety is assessed.
    if event_scan is None:
        event_scan = ScanResult(ticker=ticker, result="SKIPPED", scanned_at=as_of)
    triggered = str(signal) == "TRIGGERED"
    cap = apply_event_cap(event_scan, step5_triggered=triggered)
    row["event_scan"] = {
        "result": event_scan.result,
        "pending_mna": event_scan.pending_mna,
        "completed_mna_within_4q": event_scan.completed_mna_within_4q,
        "sources": event_scan.sources,
        "scanned_at": event_scan.scanned_at,
        "reasons": event_scan.reasons,
    }
    if cap["verdict_cap"]:
        row["verdict_cap"] = cap["verdict_cap"]
    row["event_t1_blocked"] = cap["t1_blocked"]
    row["t1_blocked"] = cap["t1_blocked"]
    # Event-scan T1/order-gate blockers are kept on the row for the order
    # gate, but excluded from the verdict-affecting set (their verdict
    # impact is already represented via verdict_cap + event_t1_blocked).
    event_order_blockers = list(cap["blockers"])
    for r in cap["reasons"]:
        notes.append(r)
    if event_scan.completed_mna_within_4q:
        notes.append("completed_merger_within_4q")

    # WS-2: sector-aware payout-safety triad. completed_merger_within_4q now
    # flows from the event scan (High3) so FITB/Comerica GAAP distortion is
    # caught from the real path, not only when financials carries the flag.
    if financials is not None:
        # FMP industry is finer than sector (issue #771): insurers hide
        # under "Financial Services", REITs under "Real Estate". Industry
        # comes from the profile first, then the financials dict.
        safety = assess_payout_safety(
            sector=financials.get("sector") or (profile or {}).get("sector"),
            industry=financials.get("industry") or (profile or {}).get("industry"),
            sector_kind_override=financials.get("sector_kind_override"),
            annual_dividend=annual_dividend,
            gaap_eps=financials.get("gaap_eps"),
            adjusted_eps=financials.get("adjusted_eps"),
            adjusted_eps_source=financials.get("adjusted_eps_source", "UNAVAILABLE"),
            fcf_per_share=financials.get("fcf_per_share"),
            completed_merger_within_4q=bool(
                financials.get("completed_merger_within_4q", False)
                or event_scan.completed_mna_within_4q
            ),
            bank_metrics=financials.get("bank_metrics"),
            utility_metrics=financials.get("utility_metrics"),
            insurer_metrics=financials.get("insurer_metrics"),
            reit_metrics=financials.get("reit_metrics"),
        )
        manual_errors = financials.get("manual_financials_errors", [])
        if manual_errors:
            safety.blockers.extend(manual_errors)
            safety.reasons.extend(manual_errors)
            if safety.safety_verdict != "FAIL":
                safety.safety_verdict = "HOLD-REVIEW"
        row["payout_safety"] = {
            "sector_kind": safety.sector_kind,
            "sector_kind_source": safety.sector_kind_source,
            "safety_verdict": safety.safety_verdict,
            "gaap_eps_payout": safety.gaap_eps_payout,
            "adjusted_eps_payout": safety.adjusted_eps_payout,
            "fcf_payout": safety.fcf_payout,
            "affo_payout": safety.affo_payout,
            "adjusted_eps_source": safety.adjusted_eps_source,
            "gaap_adj_divergence": safety.gaap_adj_divergence,
            "one_off_flag": safety.one_off_flag,
            "reasons": safety.reasons,
        }
        pre_order_blockers.extend(safety.blockers)
        if safety.one_off_flag:
            notes.append("gaap_one_off")

    order_blockers = sorted(set(pre_order_blockers) | set(event_order_blockers))
    if order_blockers:
        row["pre_order_blockers"] = order_blockers

    # WS-5: synthesize the actionable verdict tier. Verdict-affecting
    # blockers exclude pure event-scan order blockers (cap handles them).
    safety_v = row.get("payout_safety", {}).get("safety_verdict")
    final = synthesize_verdict(
        step1_verdict=row.get("step1_verdict"),
        safety_verdict=safety_v,
        event_verdict_cap=row.get("verdict_cap"),
        event_t1_blocked=bool(row.get("t1_blocked", False)),
        pre_order_blockers=sorted(set(pre_order_blockers)),
    )
    row["verdict"] = final.verdict
    row["t1_blocked"] = final.t1_blocked or bool(target_withheld_reason)
    row["verdict_reasons"] = final.reasons
    row["order_ready"] = order_ready(row, order_blockers)
    row["provenance"] = {
        "price_source": "fmp_quote" if quote else None,
        "price_date": price_date,
        "dividend_source": "fmp_stock_dividend" if dividend_history is not None else "unavailable",
        "dividend_dates_used": (basis.dividend_dates_used if basis else []),
        "payout_source": (financials or {}).get("adjusted_eps_source", "UNAVAILABLE"),
        "event_scan_result": (event_scan.result if event_scan else "NOT_SCANNED"),
        "event_scan_checked_at": (event_scan.scanned_at if event_scan else None),
        # 7th-review: audit the COMPLETE unresolved-blocker set (incl.
        # event-scan order blockers), matching row["pre_order_blockers"];
        # synthesize() intentionally consumes only the verdict-affecting
        # subset, but the audit trail must not under-report the T1 gate.
        "unresolved_blockers": order_blockers,
        "manual_financials": (financials or {}).get("manual_financials_provenance", {}),
        "manual_financials_errors": (financials or {}).get("manual_financials_errors", []),
        "evidence_refs": [],  # populated by Claude per SKILL.md source hierarchy
    }

    return row


def order_ready(row: dict[str, Any], blockers: list[str]) -> bool:
    """Conservative screening gate; never a broker authorization."""
    return bool(
        row.get("signal") == "TRIGGERED"
        and row.get("verdict") in {"CLEAN-PASS", "CONDITIONAL-PASS"}
        and row.get("t1_blocked") is False
        and not blockers
    )


def render_markdown(rows: list[dict[str, Any]], as_of: str, alpha_pp: float) -> str:
    counts = {"TRIGGERED": 0, "WAIT": 0, "ASSUMPTION-REQUIRED": 0}
    verdict_counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("signal", "ASSUMPTION-REQUIRED"))
        counts[status] = counts.get(status, 0) + 1
        v = row.get("verdict")
        if v:
            verdict_counts[v] = verdict_counts.get(v, 0) + 1

    verdict_lines = [f"- {v}: `{verdict_counts[v]}`" for v in VERDICTS if v in verdict_counts]

    lines = [
        "# Kanchi Entry Signals",
        "",
        f"- as_of: `{as_of}`",
        f"- alpha_pp: `{alpha_pp:.2f}`",
        f"- ticker_count: `{len(rows)}`",
        "",
        "## Verdict Summary (WS-5 actionable tier)",
        "",
        *(verdict_lines or ["- (no verdicts; run with --yield-floor)"]),
        "",
        "## Step-5 Timing Summary",
        "",
        f"- TRIGGERED: `{counts.get('TRIGGERED', 0)}`",
        f"- WAIT: `{counts.get('WAIT', 0)}`",
        f"- ASSUMPTION-REQUIRED: `{counts.get('ASSUMPTION-REQUIRED', 0)}`",
        "",
        "## Signals",
        "",
        "> Order Ready is the aggregate readiness gate; false whenever any blocker remains. "
        "Verdict/T1-Blocked explain the result. `signal` is only "
        "Step-5 timing — never act on it alone (a TRIGGERED row can be "
        "HOLD-REVIEW / T1-blocked).",
        "",
        "| Ticker | Verdict | Order Ready | T1 Blocked | Signal | Price | Price Date | Reg Yield% | "
        "TTM Yield% | Step1 | Safety | Event Scan | Pre-order Blockers |",
        "|---|---|---|---|---:|---|---:|---:|---|---|---|---|---|",
    ]

    for row in rows:
        db = row.get("dividend_basis", {})
        ps = row.get("payout_safety", {})
        ev = row.get("event_scan", {})
        blockers = ";".join(row.get("pre_order_blockers", [])) or "-"
        lines.append(
            "| {ticker} | {verdict} | {ready} | {t1} | {signal} | {price} | {pdate} | {ry} | "
            "{ty} | {s1} | {safety} | {ev} | {blk} |".format(
                ticker=row.get("ticker", ""),
                verdict=row.get("verdict", "-"),
                ready="YES" if row.get("order_ready") else "no",
                t1="YES" if row.get("t1_blocked") else "no",
                signal=row.get("signal", ""),
                price=row.get("price", ""),
                pdate=row.get("price_date") or "-",
                ry=db.get("regular_forward_yield_pct", ""),
                ty=db.get("ttm_yield_pct", ""),
                s1=row.get("step1_verdict", "-"),
                safety=ps.get("safety_verdict", "-"),
                ev=ev.get("result", "NOT_SCANNED"),
                blk=blockers,
            )
        )

    for row in rows:
        if row.get("target_withheld_reason"):
            lines.extend(
                [
                    "",
                    f"- {row['ticker']}: target withheld: "
                    f"`{row['target_withheld_reason']}`; numerator "
                    f"`{row['annual_dividend_basis']}`, historical average "
                    f"`{row['historical_yield_basis']}`.",
                ]
            )
    for row in rows:
        yh = row.get("yield_history")
        if yh and row.get("yield_basis") == "regular_only_reconstructed":
            lines.extend(
                [
                    "",
                    f"- {row['ticker']}: 5y average yield `{row.get('avg_5y_yield_pct')}%` "
                    f"(`{row['yield_basis']}`, `{yh.get('method')}`), window "
                    f"`{yh.get('window_start')}` to `{yh.get('window_end')}`, "
                    f"{yh.get('observation_count')}/{yh.get('expected_observations')} "
                    f"month-end observations, coverage `{yh.get('coverage_ratio')}`.",
                ]
            )
        elif yh and row.get("target_withheld_reason"):
            lines.extend(
                [
                    "",
                    f"- {row['ticker']}: yield history `{yh.get('status')}` "
                    f"({yh.get('observation_count')}/{yh.get('expected_observations')} "
                    f"observations): {', '.join(yh.get('reasons') or []) or '-'}.",
                ]
            )
    for row in rows:
        db = row.get("dividend_basis") or {}
        lines.extend(
            [
                "",
                f"- {row['ticker']}: dividend history `{db.get('status')}`, "
                f"amount basis `{db.get('dividend_amount_basis')}`; "
                f"{', '.join(db.get('reasons') or []) or '-'}.",
            ]
        )
    for row in rows:
        if row.get("price_date_mismatch"):
            lines.extend(
                [
                    "",
                    f"- {row['ticker']}: price as of `{row.get('price_date')}` "
                    f"differs from run as_of `{as_of}`.",
                ]
            )
    lines.append("")
    return "\n".join(lines)


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    # Verdict/blocker columns are first-class so a CSV-only operator sees
    # the same actionable gate as the JSON (7th-review High).
    fieldnames = [
        "ticker",
        "verdict",
        "order_ready",
        "event_t1_blocked",
        "t1_blocked",
        "signal",
        "step1_verdict",
        "payout_safety_verdict",
        "event_scan_result",
        "pre_order_blockers",
        "price",
        "price_date",
        "price_date_mismatch",
        "annual_dividend_per_share",
        "regular_forward_yield_pct",
        "ttm_yield_pct",
        "cut_confirmation_required",
        "dividend_amount_basis",
        "dividend_history_status",
        "cut_amount_basis",
        "original_dividend_currency",
        "current_yield_pct",
        "avg_5y_yield_pct",
        "alpha_pp",
        "target_yield_pct",
        "buy_target_price",
        "drop_needed_pct",
        "yield_observation_count",
        "annual_dividend_basis",
        "historical_yield_basis",
        "yield_basis",
        "target_withheld_reason",
        "provider_avg_5y_yield_pct",
        "provider_yield_observation_count",
        "yield_history_status",
        "yield_window_start",
        "yield_window_end",
        "yield_coverage_ratio",
        "yield_method",
        "notes",
    ]

    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            db = row.get("dividend_basis", {})
            ps = row.get("payout_safety", {})
            ev = row.get("event_scan", {})
            output = dict(row)
            output["notes"] = ",".join(output.get("notes", []))
            output["pre_order_blockers"] = ";".join(row.get("pre_order_blockers", []))
            output["regular_forward_yield_pct"] = db.get("regular_forward_yield_pct")
            output["ttm_yield_pct"] = db.get("ttm_yield_pct")
            output["dividend_amount_basis"] = db.get("dividend_amount_basis", "unavailable")
            output["dividend_history_status"] = db.get("status", "ASSUMPTION-REQUIRED")
            output["cut_confirmation_required"] = db.get("cut_confirmation_required", False)
            output["cut_amount_basis"] = db.get("cut_amount_basis", "unconfirmed")
            output["original_dividend_currency"] = db.get("original_dividend_currency")
            output["payout_safety_verdict"] = ps.get("safety_verdict")
            output["event_scan_result"] = ev.get("result", "NOT_SCANNED")
            yh = row.get("yield_history") or {}
            output["yield_history_status"] = yh.get("status")
            output["yield_window_start"] = yh.get("window_start")
            output["yield_window_end"] = yh.get("window_end")
            output["yield_coverage_ratio"] = yh.get("coverage_ratio")
            output["yield_method"] = yh.get("method")
            writer.writerow(output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Kanchi Step 5 entry signals from FMP data.")
    parser.add_argument("--input", default=None, help="Path to JSON file containing tickers.")
    parser.add_argument("--tickers", default=None, help="Comma-separated ticker list.")
    parser.add_argument(
        "--alpha-pp",
        type=float,
        default=0.5,
        help="Yield alpha in percentage points (default: 0.5).",
    )
    parser.add_argument("--output-dir", default="reports", help="Directory for outputs.")
    parser.add_argument(
        "--as-of",
        default=date.today().isoformat(),
        help="As-of date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--filename-prefix",
        default="kanchi_entry_signals",
        help="Output filename prefix.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.15,
        help="Per-request wait time to reduce API throttling.",
    )
    parser.add_argument(
        "--yield-floor",
        type=float,
        default=None,
        help="Step-1 yield floor %% (e.g. 4.0 income-now, 3.0 balanced). "
        "Enables WS-1 Step-1 verdict + Data Freshness Gate.",
    )
    parser.add_argument(
        "--events-json",
        default=None,
        help="Path to a curated corporate-events JSON (WS-3 Step 4b, populated "
        "via WebSearch per SKILL.md). Absent --events-json -> SKIPPED; "
        "unknown ticker inside the events JSON -> NO_EVENT_FOUND. Both are "
        "pessimistic for TRIGGERED names (cap to HOLD-REVIEW + T1 blocked).",
    )
    parser.add_argument(
        "--financials-json",
        default=None,
        help="Sourced manual EPS/sector metrics JSON; see references/sourced-financials.md.",
    )
    parser.add_argument(
        "--yield-history-json",
        default=None,
        help="Verified per-ticker dividend rows + daily closes (+ splits) with a "
        "non-empty source, replacing the fetched rows for that ticker when "
        "rebuilding the regular-only 5-year average yield (#834). "
        "See SKILL.md.",
    )
    parser.add_argument("--profile", default=None, help="income-now | balanced | growth-first")
    parser.add_argument("--safety-bias", default=None, help="tight | medium")
    parser.add_argument("--universe-source", default=None, help="Provenance: universe origin.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tickers = load_tickers(Path(args.input) if args.input else None, args.tickers)
    if not tickers:
        raise SystemExit("No tickers provided. Use --tickers or --input.")

    supplied = {}
    if args.financials_json:
        try:
            supplied = load_financials(Path(args.financials_json), args.as_of)
        except FinancialsInputError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    supplied_history: dict[str, dict[str, Any]] = {}
    if args.yield_history_json:
        try:
            supplied_history = load_yield_history(Path(args.yield_history_json))
        except YieldHistoryInputError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        for extra in sorted(set(supplied_history) - set(tickers)):
            print(
                f"Warning: --yield-history-json has data for {extra}, which is not in this run.",
                file=sys.stderr,
            )
    try:
        price_start = fetch_window_start(args.as_of)
    except ValueError:
        print("Invalid --as-of date; expected YYYY-MM-DD.", file=sys.stderr)
        return 2

    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        raise SystemExit("FMP_API_KEY is not set.")

    client = FMPClient(api_key=api_key, sleep_seconds=args.sleep_seconds)

    quotes = client.get_batch_quotes(tickers)
    profiles = client.get_batch_profiles(tickers)

    scanner = None
    if args.events_json:
        from event_scanner import ManualEventScanner

        scanner = ManualEventScanner(args.events_json)

    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        metrics = client.get_ratios(ticker, limit=10)
        history_input = supplied_history.get(ticker)
        if history_input is not None:
            dividend_history = history_input["dividends"]
            price_rows = history_input["prices"]
            split_rows = history_input["splits"]
            history_source = history_input["source"]
        else:
            dividend_history = client.get_stock_dividend(ticker)
            price_rows = client.get_price_history(ticker, price_start, args.as_of)
            split_rows = client.get_splits(ticker)
            history_source = "fmp_stable_dividends_and_eod_prices"
        yield_history = reconstruct_regular_yield(
            dividend_history,
            price_rows,
            as_of=args.as_of,
            splits=split_rows,
            source=history_source,
        )
        event_scan = scanner.scan(ticker, args.as_of) if scanner else None
        sector = (profiles.get(ticker) or {}).get("sector")
        industry = (profiles.get(ticker) or {}).get("industry")
        financials = merge_financials(
            client.get_financials(ticker, sector=sector, industry=industry), supplied.get(ticker)
        )
        row = build_entry_row(
            ticker=ticker,
            alpha_pp=args.alpha_pp,
            quote=quotes.get(ticker),
            profile=profiles.get(ticker),
            key_metrics=metrics,
            dividend_history=dividend_history,
            floor_pct=args.yield_floor,
            financials=financials,
            event_scan=event_scan,
            as_of=args.as_of,
            yield_history=yield_history,
            split_history=split_rows,
            require_split_evidence=True,
        )
        rows.append(row)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"{args.filename_prefix}_{args.as_of}"
    json_path = output_dir / f"{prefix}.json"
    csv_path = output_dir / f"{prefix}.csv"
    md_path = output_dir / f"{prefix}.md"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": args.as_of,
        "alpha_pp": args.alpha_pp,
        "yield_floor_pct": args.yield_floor,
        "run_context": build_run_context(
            profile=args.profile,
            yield_floor_pct=args.yield_floor,
            safety_bias=args.safety_bias,
            universe_source=args.universe_source,
            excluded_asset_types=None,
        ),
        "ticker_count": len(tickers),
        "api_calls": client.api_calls,
        "rows": rows,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(rows, csv_path)
    md_path.write_text(
        render_markdown(rows, as_of=args.as_of, alpha_pp=args.alpha_pp) + "\n", encoding="utf-8"
    )

    print(f"Wrote JSON: {json_path}")
    print(f"Wrote CSV: {csv_path}")
    print(f"Wrote MD: {md_path}")
    print(f"API calls: {client.api_calls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
