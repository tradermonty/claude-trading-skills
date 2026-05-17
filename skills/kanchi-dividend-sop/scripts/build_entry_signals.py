#!/usr/bin/env python3
"""Build Kanchi Step 5 entry signals using live FMP data."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections.abc import Iterable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dividend_basis import analyze_dividends, step1_decision
from event_scanner import ScanResult, apply_event_cap
from payout_safety import assess_payout_safety
from thresholds import SCHEMA_VERSION, VERDICTS
from verdict import build_run_context, synthesize_verdict

FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"


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

    raw_candidates = payload.get("candidates")
    if isinstance(raw_candidates, list):
        for item in raw_candidates:
            if isinstance(item, dict):
                ticker = str(item.get("ticker", "")).strip().upper()
                if ticker and ticker not in tickers:
                    tickers.append(ticker)
            else:
                ticker = str(item).strip().upper()
                if ticker and ticker not in tickers:
                    tickers.append(ticker)

    raw_tickers = payload.get("tickers")
    if isinstance(raw_tickers, list):
        for item in raw_tickers:
            ticker = str(item).strip().upper()
            if ticker and ticker not in tickers:
                tickers.append(ticker)

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


def chunked(values: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(values), size):
        yield values[i : i + size]


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


class FMPClient:
    def __init__(self, api_key: str, sleep_seconds: float = 0.15, timeout: int = 30):
        self.api_key = api_key
        self.sleep_seconds = sleep_seconds
        self.timeout = timeout
        self.session = requests.Session()
        self.api_calls = 0

    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any | None:
        query = dict(params or {})
        query["apikey"] = self.api_key
        url = f"{FMP_BASE_URL}/{endpoint}"
        attempts = 0

        while attempts < 2:
            attempts += 1
            try:
                response = self.session.get(url, params=query, timeout=self.timeout)
                self.api_calls += 1
            except requests.RequestException as exc:
                print(f"WARNING: Request error for {endpoint}: {exc}", file=sys.stderr)
                return None

            if response.status_code == 200:
                if self.sleep_seconds > 0:
                    time.sleep(self.sleep_seconds)
                return response.json()

            if response.status_code == 429 and attempts < 2:
                time.sleep(2.0)
                continue

            print(
                f"WARNING: FMP request failed ({response.status_code}) for {endpoint}",
                file=sys.stderr,
            )
            return None

        return None

    def get_batch_quotes(self, tickers: list[str]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for group in chunked(tickers, 50):
            data = self._get(f"quote/{','.join(group)}")
            if not isinstance(data, list):
                continue
            for row in data:
                if not isinstance(row, dict):
                    continue
                symbol = str(row.get("symbol", "")).strip().upper()
                if symbol:
                    result[symbol] = row
        return result

    def get_batch_profiles(self, tickers: list[str]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for group in chunked(tickers, 25):
            data = self._get(f"profile/{','.join(group)}")
            if isinstance(data, list):
                for row in data:
                    if not isinstance(row, dict):
                        continue
                    symbol = str(row.get("symbol", "")).strip().upper()
                    if symbol:
                        result[symbol] = row
                continue

            # Batch profile may fail for mixed symbols; fallback to per-symbol.
            for ticker in group:
                single = self._get(f"profile/{ticker}")
                if not isinstance(single, list) or not single:
                    continue
                row = single[0]
                if not isinstance(row, dict):
                    continue
                symbol = str(row.get("symbol", "")).strip().upper()
                if symbol:
                    result[symbol] = row
        return result

    def get_key_metrics(self, ticker: str, limit: int = 10) -> list[dict[str, Any]]:
        data = self._get(f"key-metrics/{ticker}", {"limit": limit})
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        return []

    def get_stock_dividend(self, ticker: str) -> list[dict[str, Any]]:
        """WS-1: full declared-dividend history (regular + special)."""
        data = self._get(f"historical-price-full/stock_dividend/{ticker}")
        if isinstance(data, dict):
            hist = data.get("historical")
            if isinstance(hist, list):
                return [row for row in hist if isinstance(row, dict)]
        return []


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
) -> dict[str, Any]:
    price = to_float((quote or {}).get("price"))

    # WS-1: prefer the regular run-rate from declared-dividend history over
    # profile.lastDiv (which is a trailing/TTM figure that lagged the latest
    # declared raise -> defect D5 -- and silently bundled specials -> D4).
    basis = None
    if dividend_history:
        basis = analyze_dividends(
            dividend_history,
            price,
            issuer_language=(profile or {}).get("issuer_language"),
            floor_pct=floor_pct,
        )

    annual_dividend = to_float((profile or {}).get("lastDiv"))
    if annual_dividend is None and key_metrics:
        annual_dividend = to_float(key_metrics[0].get("dividendPerShare"))
    if basis is not None and basis.latest_declared_annualized is not None:
        annual_dividend = basis.latest_declared_annualized

    yields_5y = normalize_metrics_yields(key_metrics, max_points=5)
    avg_yield_5y_pct_raw = average(yields_5y)
    avg_yield_5y_pct = round(avg_yield_5y_pct_raw, 2) if avg_yield_5y_pct_raw is not None else None

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
    if avg_yield_5y_pct is None:
        notes.append("avg_5y_yield_missing")
    elif len(yields_5y) < 5:
        notes.append(f"avg_5y_yield_points={len(yields_5y)}")

    row: dict[str, Any] = {
        "ticker": ticker,
        "signal": signal,
        "price": round(price, 2) if price is not None else None,
        "annual_dividend_per_share": round(annual_dividend, 4)
        if annual_dividend is not None
        else None,
        "current_yield_pct": current_yield_pct,
        "avg_5y_yield_pct": avg_yield_5y_pct,
        "alpha_pp": round(alpha_pp, 2),
        "target_yield_pct": target_yield_pct,
        "buy_target_price": buy_target_price,
        "drop_needed_pct": drop_needed_pct,
        "yield_observation_count": len(yields_5y),
        "notes": notes,
    }

    # WS-1: attach the dividend-basis breakdown + Step-1 decision.
    if basis is not None:
        row["dividend_basis"] = {
            "status": basis.status,
            "cadence": basis.cadence,
            "latest_declared_annualized": basis.latest_declared_annualized,
            "regular_annual_dividend": basis.regular_annual_dividend,
            "ttm_dividend_incl_special": basis.ttm_dividend_incl_special,
            "regular_forward_yield_pct": basis.regular_forward_yield_pct,
            "ttm_yield_pct": basis.ttm_yield_pct,
            "special_dividend_flag": basis.special_dividend_flag,
            "variable_policy_flag": basis.variable_policy_flag,
            "cut_flag": basis.cut_flag,
            "freeze_flag": basis.freeze_flag,
            "suspension_flag": basis.suspension_flag,
            "last_increase_date": basis.last_increase_date,
            "dividend_dates_used": basis.dividend_dates_used,
            "floor_borderline": basis.floor_borderline,
            "reasons": basis.reasons,
        }
        if floor_pct is not None:
            verdict, reason = step1_decision(basis, floor_pct)
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

    # WS-2: sector-aware payout-safety triad + pre-order blocker seeds.
    pre_order_blockers: list[str] = []
    if basis is not None:
        for flag in ("variable_policy_flag", "cut_flag", "freeze_flag", "suspension_flag"):
            if getattr(basis, flag):
                pre_order_blockers.append(flag)
        if basis.floor_borderline:
            pre_order_blockers.append("dividend_source_stale")
    if financials is not None:
        safety = assess_payout_safety(
            sector=financials.get("sector") or (profile or {}).get("sector"),
            annual_dividend=annual_dividend,
            gaap_eps=financials.get("gaap_eps"),
            adjusted_eps=financials.get("adjusted_eps"),
            adjusted_eps_source=financials.get("adjusted_eps_source", "UNAVAILABLE"),
            fcf_per_share=financials.get("fcf_per_share"),
            completed_merger_within_4q=bool(financials.get("completed_merger_within_4q", False)),
            bank_metrics=financials.get("bank_metrics"),
            utility_metrics=financials.get("utility_metrics"),
            insurer_metrics=financials.get("insurer_metrics"),
        )
        row["payout_safety"] = {
            "sector_kind": safety.sector_kind,
            "safety_verdict": safety.safety_verdict,
            "gaap_eps_payout": safety.gaap_eps_payout,
            "adjusted_eps_payout": safety.adjusted_eps_payout,
            "fcf_payout": safety.fcf_payout,
            "adjusted_eps_source": safety.adjusted_eps_source,
            "gaap_adj_divergence": safety.gaap_adj_divergence,
            "one_off_flag": safety.one_off_flag,
            "reasons": safety.reasons,
        }
        pre_order_blockers.extend(safety.blockers)
        if safety.one_off_flag:
            notes.append("gaap_one_off")
    # WS-3: forward/recent corporate-action layer + pessimistic cap (CR-2, #5).
    if event_scan is not None:
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
        row["t1_blocked"] = cap["t1_blocked"]
        pre_order_blockers.extend(cap["blockers"])
        for r in cap["reasons"]:
            notes.append(r)
        # completed merger feeds WS-2's GAAP-distortion linkage downstream.
        if event_scan.completed_mna_within_4q:
            notes.append("completed_merger_within_4q")

    if pre_order_blockers:
        row["pre_order_blockers"] = sorted(set(pre_order_blockers))

    # WS-5: synthesize the actionable verdict tier + provenance block.
    safety_v = row.get("payout_safety", {}).get("safety_verdict")
    final = synthesize_verdict(
        step1_verdict=row.get("step1_verdict"),
        safety_verdict=safety_v,
        event_verdict_cap=row.get("verdict_cap"),
        event_t1_blocked=bool(row.get("t1_blocked", False)),
        pre_order_blockers=sorted(set(pre_order_blockers)),
    )
    row["verdict"] = final.verdict
    row["t1_blocked"] = final.t1_blocked
    row["verdict_reasons"] = final.reasons
    row["provenance"] = {
        "price_source": "fmp_quote" if quote else None,
        "dividend_source": "fmp_stock_dividend" if dividend_history else "fmp_profile_lastDiv",
        "dividend_dates_used": (basis.dividend_dates_used if basis else []),
        "payout_source": (financials or {}).get("adjusted_eps_source", "UNAVAILABLE"),
        "event_scan_result": (event_scan.result if event_scan else "NOT_SCANNED"),
        "event_scan_checked_at": (event_scan.scanned_at if event_scan else None),
        "unresolved_blockers": sorted(set(pre_order_blockers)),
        "evidence_refs": [],  # populated by Claude per SKILL.md source hierarchy
    }

    return row


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
        "| Ticker | Signal | Price | 5Y Avg Yield% | Target Yield% | Annual Div | Buy Target Price | Drop Needed% | Notes |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]

    for row in rows:
        notes = ",".join(row.get("notes", []))
        lines.append(
            "| {ticker} | {signal} | {price} | {avg} | {target_yield} | {div} | {target_price} | {drop} | {notes} |".format(
                ticker=row.get("ticker", ""),
                signal=row.get("signal", ""),
                price=row.get("price", ""),
                avg=row.get("avg_5y_yield_pct", ""),
                target_yield=row.get("target_yield_pct", ""),
                div=row.get("annual_dividend_per_share", ""),
                target_price=row.get("buy_target_price", ""),
                drop=row.get("drop_needed_pct", ""),
                notes=notes,
            )
        )

    lines.append("")
    return "\n".join(lines)


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    fieldnames = [
        "ticker",
        "signal",
        "price",
        "annual_dividend_per_share",
        "current_yield_pct",
        "avg_5y_yield_pct",
        "alpha_pp",
        "target_yield_pct",
        "buy_target_price",
        "drop_needed_pct",
        "yield_observation_count",
        "notes",
    ]

    with output_path.open("w", newline="") as fh:
        # extrasaction="ignore": JSON carries the rich WS-1 dividend_basis
        # sub-dict; the CSV stays a stable flat contract.
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            output = dict(row)
            output["notes"] = ",".join(output.get("notes", []))
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
        "via WebSearch per SKILL.md). Absent/unknown tickers -> NO_EVENT_FOUND "
        "(pessimistic cap on TRIGGERED names).",
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
        metrics = client.get_key_metrics(ticker, limit=10)
        dividend_history = client.get_stock_dividend(ticker)
        event_scan = scanner.scan(ticker, args.as_of) if scanner else None
        row = build_entry_row(
            ticker=ticker,
            alpha_pp=args.alpha_pp,
            quote=quotes.get(ticker),
            profile=profiles.get(ticker),
            key_metrics=metrics,
            dividend_history=dividend_history,
            floor_pct=args.yield_floor,
            event_scan=event_scan,
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
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    write_csv(rows, csv_path)
    md_path.write_text(render_markdown(rows, as_of=args.as_of, alpha_pp=args.alpha_pp) + "\n")

    print(f"Wrote JSON: {json_path}")
    print(f"Wrote CSV: {csv_path}")
    print(f"Wrote MD: {md_path}")
    print(f"API calls: {client.api_calls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
