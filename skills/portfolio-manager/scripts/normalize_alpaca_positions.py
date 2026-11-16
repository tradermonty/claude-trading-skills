#!/usr/bin/env python3
"""Normalize saved Alpaca positions for a read-only reconciliation comparison.

Completeness, account attribution and capture time are operator assertions.
No broker connection, orders or trader-memory changes are performed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

from reconcile_positions import (
    SnapshotError,
    _decimal_text,
    _quantity,
    _read_snapshot,
    _snapshot,
)


def normalize(payload: object, account_scope: str, as_of: str, *, complete: bool = False) -> dict:
    """Convert every native equity position; never infer missing completeness."""
    header = {
        "schema_version": 1,
        "account_scope": account_scope,
        "as_of": as_of,
        "complete": complete,
        "positions": [],
    }
    account, stamp, _ = _snapshot(header, "broker")
    if not isinstance(payload, list):
        raise SnapshotError("broker: saved positions must be an explicit complete list")
    positions = []
    for index, row in enumerate(payload):
        label = f"broker: position {index}"
        if not isinstance(row, dict) or row.get("asset_class") != "us_equity":
            raise SnapshotError(f"{label}: only explicit us_equity instruments are supported")
        if "currency" in row and row["currency"] != "USD":
            raise SnapshotError(f"{label}: currency must be USD when supplied")
        side = row.get("side")
        if side not in ("long", "short"):
            raise SnapshotError(f"{label}: side must be long or short")
        qty = row.get("qty")
        if (
            not isinstance(qty, str)
            or len(qty) > 64
            or re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", qty) is None
        ):
            raise SnapshotError(f"{label}: qty must be a plain decimal string up to 64 characters")
        signed = Decimal(qty)
        if (side == "long" and signed <= 0) or (side == "short" and signed >= 0):
            raise SnapshotError(f"{label}: qty sign must agree with side and be nonzero")
        try:
            # abs()/normalize() can round with the caller's decimal context.
            quantity = _quantity(signed.copy_abs())
        except SnapshotError as exc:
            raise SnapshotError(f"{label}: {exc}") from None
        positions.append(
            {
                "symbol": row.get("symbol"),
                "asset_type": "equity",
                "direction": side.upper(),
                "quantity": _decimal_text(quantity),
            }
        )
    header.update(account_scope=account, as_of=stamp, positions=positions)
    _, _, validated = _snapshot(header, "broker")
    header["positions"] = [
        {
            "symbol": symbol,
            "asset_type": "equity",
            "direction": row["direction"],
            "quantity": _decimal_text(row["quantity"]),
        }
        for symbol, row in sorted(validated.items())
    ]
    return header


def _write_new_snapshot(output: Path, encoded: str) -> None:
    """Publish complete bytes without replacing any existing destination."""
    staged = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=".alpaca-reconciliation-",
            delete=False,
        ) as stream:
            staged = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        # Same-directory hardlink is exclusive and atomic on supported filesystems.
        # Unsupported filesystems fail safely; never fall back to an overwrite.
        os.link(staged, output)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--positions-json", required=True, type=Path, help="Saved native positions list"
    )
    parser.add_argument(
        "--account-scope", required=True, help="Operator-verified non-sensitive account alias"
    )
    parser.add_argument("--as-of", required=True, help="Actual capture instant with timezone")
    parser.add_argument(
        "--confirm-complete",
        action="store_true",
        required=True,
        help="Operator confirms every position in this account is represented",
    )
    parser.add_argument(
        "--output", type=Path, help="New snapshot file in an existing private directory"
    )
    args = parser.parse_args(argv)
    try:
        result = normalize(
            _read_snapshot(args.positions_json, "broker"),
            args.account_scope,
            args.as_of,
            complete=args.confirm_complete,
        )
    except SnapshotError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output is None:
        print(encoded, end="")
        return 0
    try:
        _write_new_snapshot(args.output, encoded)
    except FileExistsError:
        print("ERROR: Output already exists; use a new snapshot path", file=sys.stderr)
        return 1
    except OSError:
        print("ERROR: Cannot write normalized broker snapshot", file=sys.stderr)
        return 1
    print("Normalized broker snapshot written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
