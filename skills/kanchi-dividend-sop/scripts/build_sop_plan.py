#!/usr/bin/env python3
"""Generate a deterministic Kanchi SOP planning markdown file."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any


def parse_ticker_csv(raw: str) -> list[str]:
    tickers: list[str] = []
    for part in raw.split(","):
        value = part.strip().upper()
        if not value:
            continue
        if value not in tickers:
            tickers.append(value)
    return tickers


def normalize_candidates(payload: dict[str, Any]) -> list[dict[str, str]]:
    raw = payload.get("candidates")
    if isinstance(raw, list):
        normalized: list[dict[str, str]] = []
        for item in raw:
            if isinstance(item, str):
                ticker = item.strip().upper()
                if ticker:
                    normalized.append({"ticker": ticker, "bucket": "unassigned"})
            elif isinstance(item, dict):
                ticker = str(item.get("ticker", "")).strip().upper()
                bucket = str(item.get("bucket", "unassigned")).strip().lower() or "unassigned"
                if ticker:
                    normalized.append({"ticker": ticker, "bucket": bucket})
        return normalized
    return []


def load_candidates(
    input_path: Path | None, tickers_csv: str | None
) -> tuple[list[dict[str, str]], str]:
    if input_path:
        payload = json.loads(input_path.read_text())
        profile = str(payload.get("profile", "balanced")).strip().lower() or "balanced"
        candidates = normalize_candidates(payload)
        if candidates:
            return candidates, profile
        fallback = payload.get("tickers", [])
        if isinstance(fallback, list):
            candidates = [
                {"ticker": str(item).strip().upper(), "bucket": "unassigned"}
                for item in fallback
                if str(item).strip()
            ]
            return candidates, profile
        return [], profile

    if tickers_csv:
        return (
            [
                {"ticker": ticker, "bucket": "unassigned"}
                for ticker in parse_ticker_csv(tickers_csv)
            ],
            "balanced",
        )

    return [], "balanced"


def render_markdown(candidates: list[dict[str, str]], as_of: str, profile: str) -> str:
    lines = [
        "# Kanchi SOP Plan",
        "",
        f"- as_of: `{as_of}`",
        f"- profile: `{profile}`",
        f"- candidate_count: `{len(candidates)}`",
        "",
        "## Candidate Universe",
        "",
        "| Ticker | Bucket | Step1 | Step2 | Step3 | Step4 | Step5 |",
        "|---|---|---|---|---|---|---|",
    ]

    for item in candidates:
        lines.append(
            "| {ticker} | {bucket} | todo | todo | todo | todo | todo |".format(
                ticker=item["ticker"],
                bucket=item["bucket"],
            )
        )

    lines.extend(
        [
            "",
            "## Pullback Entry Notes",
            "",
            "- Default split order: `40% -> 30% -> 30%`",
            "- Default yield alpha: `+0.5pp` vs 5y average yield.",
            "- Add one-line invalidation per ticker before finalizing orders.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Kanchi SOP plan markdown.")
    parser.add_argument("--input", help="Path to JSON input with candidates/tickers.", default=None)
    parser.add_argument("--tickers", help="Comma-separated ticker list.", default=None)
    parser.add_argument("--output-dir", default="reports", help="Output directory path.")
    parser.add_argument(
        "--as-of", default=date.today().isoformat(), help="As-of date (YYYY-MM-DD)."
    )
    parser.add_argument("--filename", default=None, help="Optional output filename.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input) if args.input else None
    candidates, profile = load_candidates(input_path, args.tickers)
    if not candidates:
        raise SystemExit(
            "No candidates found. Provide --tickers or --input with candidates/tickers."
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = args.filename or f"kanchi_sop_plan_{args.as_of}.md"
    output_path = output_dir / filename
    output_path.write_text(render_markdown(candidates, args.as_of, profile) + "\n")
    print(f"Wrote SOP plan: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
