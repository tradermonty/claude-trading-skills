#!/usr/bin/env python3
"""Produce a limited, offline equity-holdings allocation report from CSV."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import TextIO

REQUIRED = {"symbol", "asset_type", "quantity", "direction", "price", "currency"}
OPTIONAL = {"cost_basis", "account"}
LIMITATIONS = [
    "Local CSV assertions only; identity, completeness and price freshness are unverified.",
    "USD equities only. Weights use gross holdings value, not account equity.",
    "Cash, leverage, sector/beta, historical returns and trading recommendations are unavailable.",
    "P&L is per position only; missing per-share cost basis means unavailable, not zero.",
    "No broker access, order execution, or trader-memory changes. Not a reconciliation gate.",
    "Navigator and workflow integration remain unshipped (#512).",
]


class CsvError(ValueError):
    """Safe input diagnostic without user-provided values."""


def _number(raw: str, row: int, field: str, *, zero: bool = False) -> Decimal:
    label = f"row {row}: invalid {field}"
    if len(raw) > 32 or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,12})?", raw):
        raise CsvError(label)
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise CsvError(label) from exc
    if not value.is_finite() or value > Decimal("1e12") or value < 0:
        raise CsvError(label)
    if not zero and value == 0:
        raise CsvError(label)
    return value


def _text(value: Decimal) -> str:
    result = format(value, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def build_report(stream: TextIO, as_of: str) -> dict:
    """Validate all input before returning sanitized deterministic output."""
    try:
        stamp = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        if stamp.utcoffset() is None:
            raise ValueError
        stamp = stamp.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError) as exc:
        raise CsvError("as-of must be a timezone-aware ISO timestamp") from exc
    reader = csv.reader(stream, strict=True)
    positions = []
    seen = set()
    try:
        headers = next(reader, [])
        if (
            len(headers) != len(set(headers))
            or not REQUIRED <= set(headers)
            or not set(headers) <= REQUIRED | OPTIONAL
        ):
            raise CsvError("invalid CSV headers; see the documented holdings schema")
        # At most 10,000 rows, fields <= 1e12 with <=12 fractional digits:
        # products/sums fit exactly in 80 digits; only weight ratios are rounded.
        with localcontext() as ctx:
            ctx.prec = 80
            gross = Decimal(0)
            net = Decimal(0)
            for index, values in enumerate(reader, 2):
                if index > 10001:
                    raise CsvError("CSV row limit is 10000 holdings")
                if len(values) != len(headers):
                    raise CsvError(f"row {index}: wrong field count")
                row = dict(zip(headers, values))
                symbol = row["symbol"].strip().upper()
                if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,23}", symbol):
                    raise CsvError(f"row {index}: invalid equity symbol")
                if symbol in seen:
                    raise CsvError(f"row {index}: duplicate symbol; consolidate lots manually")
                seen.add(symbol)
                if row["asset_type"] != "equity" or row["currency"] != "USD":
                    raise CsvError(f"row {index}: only USD equity holdings are supported")
                direction = row["direction"]
                if direction not in ("LONG", "SHORT"):
                    raise CsvError(f"row {index}: direction must be LONG or SHORT")
                quantity = _number(row["quantity"], index, "quantity")
                price = _number(row["price"], index, "price")
                cost = row.get("cost_basis", "")
                basis = _number(cost, index, "cost_basis", zero=True) if cost else None
                sign = Decimal(1) if direction == "LONG" else Decimal(-1)
                value = quantity * price
                gross += value
                net += sign * value
                positions.append(
                    {
                        "symbol": symbol,
                        "asset_type": "equity",
                        "direction": direction,
                        "quantity": _text(quantity),
                        "price": _text(price),
                        "currency": "USD",
                        "cost_basis": _text(basis) if basis is not None else None,
                        "gross_market_value": _text(value),
                        "net_market_value": _text(sign * value),
                        "unrealized_pnl": _text(sign * quantity * (price - basis))
                        if basis is not None
                        else None,
                    }
                )
            if not positions:
                raise CsvError("CSV must contain at least one holding")
            for position in positions:
                weight = Decimal(position["gross_market_value"]) / gross * 100
                position["gross_weight_pct"] = _text(weight.quantize(Decimal("0.000001")))
    except csv.Error as exc:
        raise CsvError("malformed CSV or field exceeds parser limit") from exc
    return {
        "schema_version": 1,
        "report_type": "holdings_allocation_only",
        "provenance": {"source": "local_csv", "as_of": stamp, "freshness": "operator_asserted"},
        "currency": "USD",
        "gross_holdings_value": _text(gross),
        "net_holdings_value": _text(net),
        "positions": sorted(positions, key=lambda p: p["symbol"]),
        "limitations": list(LIMITATIONS),
    }


def render_markdown(report: dict) -> str:
    """Render only validated fields, never the input filename or account column."""
    lines = [
        "# Offline CSV holdings review",
        "",
        f"Source: local_csv; as-of: {report['provenance']['as_of']} (operator asserted)",
        "",
        f"Gross holdings value (USD): {report['gross_holdings_value']}",
        f"Signed net holdings value (USD): {report['net_holdings_value']}",
        "",
        "| Symbol | Direction | Quantity | Gross value USD | Gross weight % | Unrealized P&L USD |",
        "|---|---|---|---|---|---|",
    ]
    for p in report["positions"]:
        pnl = p["unrealized_pnl"] if p["unrealized_pnl"] is not None else "unavailable"
        lines.append(
            f"| {p['symbol']} | {p['direction']} | {p['quantity']} | "
            f"{p['gross_market_value']} | {p['gross_weight_pct']} | {pnl} |"
        )
    lines.extend(["", "## Limitations", ""] + [f"- {x}" for x in report["limitations"]])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("reports"))
    args = parser.parse_args(argv)
    try:
        with args.input.open(encoding="utf-8-sig", newline="") as stream:
            report = build_report(stream, args.as_of)
        targets = [args.output_dir / f"portfolio_csv_review.{ext}" for ext in ("json", "md")]
        if any(
            path.resolve() == args.input.resolve() or (path.exists() and path.samefile(args.input))
            for path in targets
        ):
            raise CsvError("output must not overwrite the input file")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        contents = [json.dumps(report, indent=2) + "\n", render_markdown(report)]
        for target, content in zip(targets, contents):
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=args.output_dir, delete=False
                ) as stream:
                    temporary = Path(stream.name)
                    stream.write(content)
                temporary.replace(target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
    except CsvError as exc:
        print(f"CSV review: {exc}", file=sys.stderr)
        return 1
    except (OSError, UnicodeError, RuntimeError):
        print(
            "CSV review: unable to read input or write report; check encoding and permissions",
            file=sys.stderr,
        )
        return 1
    print("Offline holdings review written (JSON and Markdown).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
