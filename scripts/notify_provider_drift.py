#!/usr/bin/env python3
"""Persist fatal FMP contract drift. Read-only unless --apply is explicit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path


class NotificationError(ValueError):
    """Invalid evidence or an incomplete notification operation."""


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.:-]{0,255}", value):
        raise NotificationError("Invalid report identifier")
    return value


def anomaly_code(value):
    if isinstance(value, str) and value.startswith("canonical_absent_legacy_present:"):
        parts = value.removeprefix("canonical_absent_legacy_present:").split("->")
        if len(parts) != 2:
            raise NotificationError("Invalid report identifier")
        for part in parts:
            identifier(part)
        return value
    return identifier(value)


def authored_by_bot(item):
    user = item.get("user")
    return (
        isinstance(user, dict)
        and user.get("login") == "github-actions[bot]"
        and user.get("type") == "Bot"
    )


def parse_report(data):
    """Validate the entire envelope before allowing even the first API write."""
    if (
        not isinstance(data, dict)
        or data.get("provider") != "fmp"
        or type(data.get("ok")) is not bool
    ):
        raise NotificationError("Expected an FMP canary report")
    contracts = data.get("contracts")
    if not isinstance(contracts, dict) or not contracts:
        raise NotificationError("Missing contract evidence")
    fatal = Counter()
    for name, result in contracts.items():
        identifier(name)
        if not isinstance(result, dict) or type(result.get("ok")) is not bool:
            raise NotificationError("Invalid contract result")
        status = result.get("status")
        if (
            type(status) is not int
            or not (status == -1 or 100 <= status <= 599)
            or type(result.get("rows")) is not int
            or result["rows"] < 0
        ):
            raise NotificationError("Invalid response evidence")
        anomalies = result.get("anomalies")
        deprecations = result.get("deprecations")
        if not isinstance(anomalies, list) or not isinstance(deprecations, list):
            raise NotificationError("Invalid anomaly evidence")
        for entries, severity in ((anomalies, "fatal"), (deprecations, "deprecation")):
            for item in entries:
                if not isinstance(item, dict):
                    raise NotificationError("Invalid anomaly")
                code = anomaly_code(item.get("code"))
                if (
                    item.get("severity") != severity
                    or type(item.get("count")) is not int
                    or item["count"] < 1
                ):
                    raise NotificationError("Invalid anomaly severity/count")
                if severity == "fatal" and status == 200:
                    fatal[name, code] += item["count"]
        if result["ok"] != (status == 200 and not anomalies):
            raise NotificationError("Inconsistent contract outcome")
    if data["ok"] != all(result["ok"] for result in contracts.values()):
        raise NotificationError("Inconsistent report outcome")
    return [(name, code, count) for (name, code), count in sorted(fatal.items())]


def validate_destination(repository, run_url):
    if not isinstance(repository, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repository
    ):
        raise NotificationError("Invalid repository")
    if repository.split("/")[1] in {".", ".."}:
        raise NotificationError("Invalid repository")
    if not isinstance(run_url, str) or not re.fullmatch(
        re.escape(f"https://github.com/{repository}/actions/runs/") + r"[1-9][0-9]*", run_url
    ):
        raise NotificationError("Expected a run URL in the target GitHub repository")


def gh_api(method, path, payload=None):
    if not os.environ.get("GH_TOKEN"):
        raise NotificationError("GH_TOKEN is required to apply notifications")
    args = ["gh", "api", "--hostname", "github.com", "--method", method, path]
    if payload is not None:
        args += ["--input", "-"]
    try:
        result = subprocess.run(
            args,
            input=json.dumps(payload) if payload is not None else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NotificationError(f"GitHub {method} could not complete") from exc
    if result.returncode:
        # gh stderr can contain request/credential details. Never print it.
        raise NotificationError(f"GitHub {method} failed")
    try:
        return json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise NotificationError(f"GitHub {method} returned invalid JSON") from exc


def pages(api, path):
    for page in range(1, 1001):
        items = api("GET", f"{path}{'&' if '?' in path else '?'}page={page}&per_page=100")
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise NotificationError("Invalid GitHub list response")
        yield from items
        if len(items) < 100:
            return
    raise NotificationError("GitHub pagination limit exceeded")


def region(body, start, end):
    if not isinstance(body, str) or body.count(start) != 1 or body.count(end) != 1:
        raise NotificationError("Tracking issue has ambiguous managed markers")
    first = body.index(start)
    last = body.index(end) + len(end)
    if first >= last - len(end):
        raise NotificationError("Tracking issue has reversed managed markers")
    return first, last


def notify(data, repository, run_url, api=gh_api):
    anomalies = parse_report(data)
    validate_destination(repository, run_url)
    if not anomalies:
        return 0
    base = f"repos/{repository}"
    issues = list(pages(api, f"{base}/issues?state=all"))
    # Resolve every target before mutation, so malformed/duplicate markers cannot
    # leave only a subset of this report recorded.
    plans = []
    for contract, code, count in anomalies:
        key = hashlib.sha256(f"{contract}\0{code}".encode()).hexdigest()
        start, end = f"<!-- fmp-drift:{key}:start -->", f"<!-- fmp-drift:{key}:end -->"
        matches = [
            i
            for i in issues
            if "pull_request" not in i and authored_by_bot(i) and start in (i.get("body") or "")
        ]
        if len(matches) > 1:
            raise NotificationError("Multiple issues match one drift key; resolve manually")
        managed = (
            f"{start}\n## Fatal FMP contract drift\n\n"
            f"Contract: `{contract}`\n\nCode: `{code}`\n\nOccurrences: {count}\n\n"
            f"Latest run: {run_url}\n\n"
            "Contract drift remains report-only; investigate before changing the contract.\n"
            f"{end}"
        )
        issue = matches[0] if matches else None
        bounds = region(issue["body"], start, end) if issue else None
        if issue and (
            type(issue.get("number")) is not int
            or issue["number"] < 1
            or issue.get("state") not in {"open", "closed"}
        ):
            raise NotificationError("Invalid tracking issue metadata")
        previous_id = 0
        if issue:
            first, last = bounds
            old = issue["body"][first:last]
            # Run IDs increase across executions. Validate before any writes;
            # an incomplete PATCH retains the old ID and can be retried.
            previous = re.findall(
                r"^Latest run: "
                + re.escape(f"https://github.com/{repository}/actions/runs/")
                + r"([1-9][0-9]*)$",
                old,
                re.MULTILINE,
            )
            if len(previous) != 1:
                raise NotificationError("Tracking issue has invalid latest-run evidence")
            previous_id = int(previous[0])
        plans.append((contract, code, key, issue, bounds, managed, previous_id))
    owner = None
    if any(plan[3] is None for plan in plans):
        metadata = api("GET", base)
        owner_data = metadata.get("owner", {}) if isinstance(metadata, dict) else {}
        owner = owner_data.get("login")
        if owner_data.get("type") != "User" or owner != repository.split("/")[0]:
            raise NotificationError(
                "New tracking issues require a repository User owner for assignment"
            )
    for contract, code, key, issue, bounds, managed, previous_id in plans:
        if issue is None:
            api(
                "POST",
                f"{base}/issues",
                {
                    "title": f"[FMP contract drift] {contract}: {code}",
                    "body": managed + "\n\n## Maintainer notes\n",
                    "assignees": [owner],
                },
            )
            continue
        first, last = bounds
        if previous_id >= int(run_url.rsplit("/", 1)[1]):
            continue
        comments_path = f"{base}/issues/{issue['number']}/comments"
        marker = f"<!-- fmp-drift-observation:{key}:{run_url.rsplit('/', 1)[1]} -->"
        if not any(
            authored_by_bot(comment) and marker in (comment.get("body") or "")
            for comment in pages(api, comments_path)
        ):
            api("POST", comments_path, {"body": f"{marker}\nFatal drift observed again: {run_url}"})
        api(
            "PATCH",
            f"{base}/issues/{issue['number']}",
            {
                "body": issue["body"][:first] + managed + issue["body"][last:],
                "state": "open",
            },
        )
    return len(anomalies)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--run-url")
    parser.add_argument("--apply", action="store_true", help="Create/update GitHub tracking issues")
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.report.read_text(encoding="utf-8"))
        anomalies = parse_report(data)
        if args.apply:
            url = (
                args.run_url
                or f"https://github.com/{args.repository}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
            )
            notify(data, args.repository, url)
        print(f"{'Applied' if args.apply else 'Read-only'}: {len(anomalies)} fatal drift key(s)")
        return 0
    except (OSError, ValueError) as exc:
        # JSON/OSError text may echo raw input paths or provider content.
        message = (
            str(exc) if isinstance(exc, NotificationError) else "Unable to read valid canary JSON"
        )
        print(f"Drift notification failed: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
