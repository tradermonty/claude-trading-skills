#!/usr/bin/env python3
"""Generate a deterministic US dividend tax planning sheet."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


@dataclass
class PlanningRow:
    ticker: str
    instrument_type: str
    account_type: str
    hold_days_in_window: int | None
    classification: str
    location_hint: str
    note: str


def required_days(security_type: str | None) -> int:
    if str(security_type or "").strip().lower() == "preferred":
        return 91
    return 61


def classify_holding(holding: dict[str, Any]) -> PlanningRow:
    ticker = str(holding.get("ticker", "")).strip().upper() or "UNKNOWN"
    instrument_type = str(holding.get("instrument_type", "stock")).strip().lower()
    account_type = str(holding.get("account_type", "unknown")).strip().lower()
    security_type = str(holding.get("security_type", "common")).strip().lower()

    hold_days_raw = holding.get("hold_days_in_window")
    hold_days: int | None
    if hold_days_raw is None:
        hold_days = None
    else:
        hold_days = int(hold_days_raw)

    if instrument_type in {"reit", "bdc"}:
        return PlanningRow(
            ticker=ticker,
            instrument_type=instrument_type,
            account_type=account_type,
            hold_days_in_window=hold_days,
            classification="ordinary_likely",
            location_hint="tax_advantaged_preferred",
            note="distribution may include ordinary-income style components",
        )

    if instrument_type == "mlp":
        return PlanningRow(
            ticker=ticker,
            instrument_type=instrument_type,
            account_type=account_type,
            hold_days_in_window=hold_days,
            classification="out_of_scope_mlp",
            location_hint="case_by_case",
            note="check K-1 and UBTI implications before placement",
        )

    if hold_days is None:
        return PlanningRow(
            ticker=ticker,
            instrument_type=instrument_type,
            account_type=account_type,
            hold_days_in_window=hold_days,
            classification="assumption_required",
            location_hint="taxable_preferred",
            note="hold_days_in_window missing; cannot verify qualified treatment",
        )

    threshold = required_days(security_type)
    if hold_days >= threshold:
        classification = "qualified_likely"
        note = f"hold_days_in_window >= {threshold}"
    else:
        classification = "ordinary_likely"
        note = f"hold_days_in_window < {threshold}"

    return PlanningRow(
        ticker=ticker,
        instrument_type=instrument_type,
        account_type=account_type,
        hold_days_in_window=hold_days,
        classification=classification,
        location_hint="taxable_preferred",
        note=note,
    )


def render_markdown(rows: list[PlanningRow], as_of: str) -> str:
    lines = [
        "# US Dividend Tax Planning Sheet",
        "",
        f"- as_of: `{as_of}`",
        f"- holding_count: `{len(rows)}`",
        "",
        "| Ticker | Instrument | Account | Hold Days | Classification | Location Hint | Note |",
        "|---|---|---|---:|---|---|---|",
    ]
    for row in rows:
        hold_days = "" if row.hold_days_in_window is None else str(row.hold_days_in_window)
        lines.append(
            f"| {row.ticker} | {row.instrument_type} | {row.account_type} | {hold_days} | "
            f"{row.classification} | {row.location_hint} | {row.note} |"
        )

    lines.extend(
        [
            "",
            "## Open Items",
            "",
            "- Confirm final classification against broker 1099-DIV and IRS current-year guidance.",
            "- Escalate unresolved assumptions to CPA/tax advisor.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(path: Path, rows: list[PlanningRow]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "ticker",
                "instrument_type",
                "account_type",
                "hold_days_in_window",
                "classification",
                "location_hint",
                "note",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.ticker,
                    row.instrument_type,
                    row.account_type,
                    row.hold_days_in_window if row.hold_days_in_window is not None else "",
                    row.classification,
                    row.location_hint,
                    row.note,
                ]
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build US dividend tax planning artifacts.")
    parser.add_argument("--input", required=True, help="Path to JSON input with holdings list.")
    parser.add_argument("--output-dir", default="reports", help="Output directory.")
    parser.add_argument("--as-of", default=date.today().isoformat(), help="As-of date.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.loads(Path(args.input).read_text())
    holdings = payload.get("holdings", [])
    if not isinstance(holdings, list) or not holdings:
        raise SystemExit("Input JSON must include a non-empty holdings list.")

    rows = [classify_holding(item) for item in holdings]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = output_dir / f"tax_planning_sheet_{args.as_of}.md"
    csv_path = output_dir / f"tax_planning_sheet_{args.as_of}.csv"
    markdown_path.write_text(render_markdown(rows, args.as_of) + "\n")
    write_csv(csv_path, rows)

    print(f"Wrote markdown: {markdown_path}")
    print(f"Wrote csv: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
