#!/usr/bin/env python3
"""Compare complete, manually normalized equity snapshots without external access."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path


class SnapshotError(ValueError):
    """Input cannot establish a comparable pair of snapshots."""


def _quantity(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise SnapshotError("quantity must be a positive decimal share count")
    text = str(value)
    if len(text) > 64:
        raise SnapshotError("quantity representation is too long")
    try:
        quantity = Decimal(text)
    except InvalidOperation as exc:
        raise SnapshotError("quantity must be a positive decimal share count") from exc
    if not quantity.is_finite() or not Decimal("1e-12") <= quantity <= Decimal("1e12"):
        raise SnapshotError("quantity must be finite and within 1e-12..1e12 shares")
    return quantity


def _snapshot(payload: object, source: str) -> tuple[str, str, dict[str, dict]]:
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int:
        raise SnapshotError(f"{source}: schema_version must be integer 1")
    if payload["schema_version"] != 1 or payload.get("complete") is not True:
        raise SnapshotError(f"{source}: schema_version=1 and complete=true are required")
    account = payload.get("account_scope")
    if not isinstance(account, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", account):
        raise SnapshotError(f"{source}: account_scope must be a non-sensitive account alias")
    stamp = payload.get("as_of")
    try:
        if not isinstance(stamp, str):
            raise ValueError
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if when.utcoffset() is None:
            raise ValueError
        stamp = when.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError) as exc:
        raise SnapshotError(f"{source}: as_of must be a timezone-aware ISO timestamp") from exc
    rows = payload.get("positions")
    if not isinstance(rows, list):
        raise SnapshotError(f"{source}: positions must be an explicit complete list")
    positions = {}
    for index, row in enumerate(rows):
        label = f"{source}: position {index}"
        if not isinstance(row, dict) or row.get("asset_type") != "equity":
            raise SnapshotError(f"{label}: only explicit equity instruments are supported")
        symbol = row.get("symbol")
        if not isinstance(symbol, str):
            raise SnapshotError(f"{label}: symbol is required")
        symbol = symbol.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,23}", symbol):
            raise SnapshotError(f"{label}: invalid equity symbol")
        direction = row.get("direction")
        if direction not in ("LONG", "SHORT"):
            raise SnapshotError(f"{label}: direction must be LONG or SHORT")
        if source == "memory" and direction != "LONG":
            raise SnapshotError(f"{label}: trader-memory equities are long-only")
        if symbol in positions:
            raise SnapshotError(f"{label}: duplicate equity identity; resolve lots manually")
        positions[symbol] = {"direction": direction, "quantity": _quantity(row.get("quantity"))}
    return account, stamp, positions


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def reconcile(broker: object, memory: object) -> dict:
    """Return a deterministic report; invalid inputs always stop the manual gate."""
    report = {
        "schema_version": 1,
        "status": "INVALID_INPUT",
        "requires_review": True,
        "can_continue": False,
        "items": [],
        "errors": [],
        "limitations": [
            "Completeness, account attribution and live freshness are operator assertions.",
            "can_continue permits manual allocation review only; it never authorizes orders.",
        ],
    }
    try:
        broker_account, broker_stamp, broker_positions = _snapshot(broker, "broker")
        memory_account, memory_stamp, memory_positions = _snapshot(memory, "memory")
        if broker_account != memory_account:
            raise SnapshotError("account_scope must match across snapshots")
        if broker_stamp != memory_stamp:
            raise SnapshotError("as_of must represent the same instant across snapshots")
    except SnapshotError as exc:
        report["errors"] = [str(exc)]
        return report
    items = []
    for symbol in sorted(broker_positions.keys() | memory_positions.keys()):
        left, right = broker_positions.get(symbol), memory_positions.get(symbol)
        if left is None:
            status = "MEMORY_ONLY"
        elif right is None:
            status = "BROKER_ONLY"
        elif left["direction"] != right["direction"]:
            status = "DIRECTION_MISMATCH"
        elif left["quantity"] != right["quantity"]:
            status = "QUANTITY_MISMATCH"
        else:
            status = "MATCH"
        items.append(
            {
                "symbol": symbol,
                "asset_type": "equity",
                "broker_quantity": _decimal_text(left["quantity"]) if left else None,
                "memory_quantity": _decimal_text(right["quantity"]) if right else None,
                "broker_direction": left["direction"] if left else None,
                "memory_direction": right["direction"] if right else None,
                "status": status,
                "requires_review": status != "MATCH",
            }
        )
    requires_review = any(item["requires_review"] for item in items)
    report.update(
        account_scope=broker_account,
        as_of=broker_stamp,
        items=items,
        status="REVIEW_REQUIRED" if requires_review else "MATCH",
        requires_review=requires_review,
        can_continue=not requires_review,
    )
    return report


def render_summary(report: dict) -> str:
    lines = [
        "# Broker / trader-memory reconciliation",
        "",
        f"Status: {report['status']}",
        f"Manual allocation review may continue: {str(report['can_continue']).lower()}",
        "",
    ]
    if "as_of" in report:
        lines.extend([f"As of: {report['as_of']}", f"Account alias: {report['account_scope']}", ""])
    lines.extend(f"- {error}" for error in report["errors"])
    if report["items"]:
        lines.extend(
            [
                "| Symbol | Broker shares | Memory shares | Broker / memory direction | Status |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for item in report["items"]:
            lines.append(
                f"| {item['symbol']} | {item['broker_quantity']} | {item['memory_quantity']} | "
                f"{item['broker_direction']} / {item['memory_direction']} | {item['status']} |"
            )
    lines.extend(["", *[f"- {note}" for note in report["limitations"]], ""])
    return "\n".join(lines)


def _unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotError("duplicate JSON object key")
        result[key] = value
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker", required=True, type=Path, help="Normalized broker JSON")
    parser.add_argument("--memory", required=True, type=Path, help="Normalized memory JSON")
    parser.add_argument(
        "--output-dir", type=Path, help="Write JSON + Markdown reports (valid input only)"
    )
    args = parser.parse_args(argv)
    try:
        snapshots = [
            json.loads(
                path.read_text(encoding="utf-8"),
                parse_float=Decimal,
                object_pairs_hook=_unique_object,
            )
            for path in (args.broker, args.memory)
        ]
        report = reconcile(*snapshots)
    except (OSError, ValueError, UnicodeError, RecursionError, InvalidOperation):
        report = reconcile(None, None)
        report["errors"] = ["Cannot read unique-key JSON snapshots; verify both input files."]
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output_dir is not None and report["status"] != "INVALID_INPUT":
        paths = [args.output_dir / f"reconciliation_report.{ext}" for ext in ("json", "md")]
        try:
            inputs = (args.broker, args.memory)
            if any(
                path.resolve() == source.resolve() or (path.exists() and path.samefile(source))
                for path in paths
                for source in inputs
            ):
                print("Report destination would overwrite an input snapshot", file=sys.stderr)
                return 1
            args.output_dir.mkdir(parents=True, exist_ok=True)
            paths[0].write_text(encoded, encoding="utf-8")
            paths[1].write_text(render_summary(report), encoding="utf-8")
        except OSError:
            print("Cannot write reconciliation reports", file=sys.stderr)
            return 1
    print(encoded, end="")
    if not report["can_continue"]:
        print(
            "Reconciliation requires manual review; stop allocation/rebalance review.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
