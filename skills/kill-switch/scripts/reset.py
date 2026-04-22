#!/usr/bin/env python3
"""Reset the kill-switch after a TRIPPED state.

Requires explicit --reason. Writes a fresh OK state file with reset metadata,
so the next watchdog run starts from clean state.

Usage:
    python3 reset.py --reason "manual review complete - account stabilized" \
      --status state/kill_switch_status.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reason", required=True,
                    help="Why is the kill-switch being reset? Logged for audit.")
    ap.add_argument("--status", type=Path,
                    default=REPO_ROOT / "state" / "kill_switch_status.json")
    ap.add_argument("--audit-log", type=Path,
                    default=REPO_ROOT / "state" / "kill_switch_resets.jsonl")
    ap.add_argument("--yes", action="store_true",
                    help="Skip interactive confirmation prompt")
    args = ap.parse_args()

    prior: dict = {}
    if args.status.exists():
        try:
            prior = json.loads(args.status.read_text())
        except (json.JSONDecodeError, OSError):
            prior = {}

    prior_status = prior.get("status", "UNKNOWN")
    if prior_status == "OK":
        print("Note: kill-switch is already OK. Reset will refresh state anyway.",
              file=sys.stderr)

    if not args.yes:
        prompt = (f"\n*** Reset kill-switch from {prior_status} to OK?\n"
                  f"*** Reason: {args.reason}\n"
                  f"Type 'RESET' to confirm: ")
        try:
            confirm = input(prompt).strip()
        except EOFError:
            print("REFUSED: no input available, pass --yes for non-interactive use",
                  file=sys.stderr)
            return 1
        if confirm != "RESET":
            print("REFUSED: confirmation not received", file=sys.stderr)
            return 1

    now = dt.datetime.utcnow().isoformat() + "Z"
    new_status = {
        "checked_at": now,
        "status": "OK",
        "reset": True,
        "reset_at": now,
        "reset_reason": args.reason,
        "prior_status": prior_status,
        "prior_reason": prior.get("reason"),
        "checks": [],
    }

    args.status.parent.mkdir(parents=True, exist_ok=True)
    args.status.write_text(json.dumps(new_status, indent=2, default=str))

    # Append to audit log
    args.audit_log.parent.mkdir(parents=True, exist_ok=True)
    audit_entry = {
        "reset_at": now,
        "reason": args.reason,
        "prior_status": prior_status,
        "prior_reason": prior.get("reason"),
    }
    with args.audit_log.open("a") as f:
        f.write(json.dumps(audit_entry) + "\n")

    print(f"Kill-switch reset OK. Audit logged to {args.audit_log}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
