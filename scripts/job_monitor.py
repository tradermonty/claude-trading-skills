#!/usr/bin/env python3
"""Automation failure notifications and independent success heartbeat checks."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

JOBS = {
    "improvement": ("logs/.skill_improvement_state.json", None, 48),
    "generation-daily": ("logs/.skill_generation_state.json", "daily", 48),
    "generation-weekly": ("logs/.skill_generation_state.json", "weekly", 24 * 14),
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def notify_failure(job, exit_code):
    """Best effort; never send command output, paths, or exception details."""
    _notify(f"Skill automation {job} failed (exit {exit_code}). Check local logs.")


def _notify(message, default_mode=""):
    mode = os.environ.get("SKILL_LOOP_NOTIFY", default_mode)
    if not mode or mode == "off":
        return
    try:
        if mode == "macos":
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    'on run argv\n display notification (item 1 of argv) with title "Skill automation"\nend run',
                    message,
                ],
                check=True,
                capture_output=True,
                timeout=5,
            )
        elif mode == "webhook":
            url = os.environ.get("SKILL_LOOP_WEBHOOK_URL", "")
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Invalid webhook configuration")
            request = urllib.request.Request(
                url,
                data=json.dumps({"text": message}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            opener = urllib.request.build_opener(NoRedirect())
            with opener.open(request, timeout=5):
                pass
        else:
            raise ValueError("Invalid notifier mode")
    except Exception:
        print("Automation notification failed; check notifier configuration.", file=sys.stderr)


def heartbeat_checks(root, now=None):
    """Return bounded, non-sensitive diagnostics without changing any state."""
    now = now or datetime.now(timezone.utc)
    results = []
    for job, (filename, mode, max_hours) in JOBS.items():
        status = "missing or invalid success timestamp"
        try:
            state = json.loads((root / filename).read_text(encoding="utf-8"))
            stamp = state["last_success_at"]
            if mode:
                stamp = stamp[mode]
            if not isinstance(stamp, str):
                raise ValueError
            success = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if success.tzinfo is None:
                raise ValueError
            age = now - success
            if age < timedelta(0):
                status = "success timestamp is in the future"
            elif age > timedelta(hours=max_hours):
                status = f"stale (over {max_hours} hours)"
            else:
                status = "ok"
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            pass
        results.append((job, status))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check-heartbeat", action="store_true")
    action.add_argument("--notify-heartbeat", action="store_true")
    action.add_argument("--notify-failure", choices=[*JOBS, "generation"])
    parser.add_argument("--exit-code", type=int, default=1)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if args.notify_failure:
        notify_failure(args.notify_failure, args.exit_code)
        return 0
    results = heartbeat_checks(args.project_root)
    for job, status in results:
        print(f"{job}: {status}")
        if args.notify_heartbeat and status != "ok":
            _notify(
                f"Skill automation {job} has no fresh success heartbeat. Check local logs.",
                default_mode="macos",
            )
    return int(any(status != "ok" for _, status in results))


if __name__ == "__main__":
    raise SystemExit(main())
