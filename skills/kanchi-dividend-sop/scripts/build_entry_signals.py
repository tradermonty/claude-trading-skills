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


def build_entry_row(
    ticker: str,
    alpha_pp: float,
    quote: dict[str, Any] | None,
    profile: dict[str, Any] | None,
    key_metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    price = to_float((quote or {}).get("price"))
    annual_dividend = to_float((profile or {}).get("lastDiv"))
    if annual_dividend is None and key_metrics:
        annual_dividend = to_float(key_metrics[0].get("dividendPerShare"))

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

    return {
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


def render_markdown(rows: list[dict[str, Any]], as_of: str, alpha_pp: float) -> str:
    counts = {"TRIGGERED": 0, "WAIT": 0, "ASSUMPTION-REQUIRED": 0}
    for row in rows:
        status = str(row.get("signal", "ASSUMPTION-REQUIRED"))
        counts[status] = counts.get(status, 0) + 1

    lines = [
        "# Kanchi Entry Signals",
        "",
        f"- as_of: `{as_of}`",
        f"- alpha_pp: `{alpha_pp:.2f}`",
        f"- ticker_count: `{len(rows)}`",
        "",
        "## Summary",
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
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
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

    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        metrics = client.get_key_metrics(ticker, limit=10)
        row = build_entry_row(
            ticker=ticker,
            alpha_pp=args.alpha_pp,
            quote=quotes.get(ticker),
            profile=profiles.get(ticker),
            key_metrics=metrics,
        )
        rows.append(row)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"{args.filename_prefix}_{args.as_of}"
    json_path = output_dir / f"{prefix}.json"
    csv_path = output_dir / f"{prefix}.csv"
    md_path = output_dir / f"{prefix}.md"

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": args.as_of,
        "alpha_pp": args.alpha_pp,
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
