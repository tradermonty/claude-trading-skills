#!/usr/bin/env python3
"""CLI for FMP provider response contracts (Issue #332).

Two subcommands:

``check`` — offline CI gate. Loads every contract under
``config/provider-contracts/``, validates its structure and fixture rows,
and confirms every owner is a real skill in ``skills-index.yaml``. Zero
network; imports with ``requests`` unavailable (the CI ``metadata`` job
installs only ``pyyaml`` + ``packaging``).

``canary`` — live, scheduled probe (see
``.github/workflows/fmp-contract-canary.yml``). Needs ``FMP_API_KEY``. Makes
one GET per contract (query-param auth via ``requests`` ``params=``, never
string-formatted into a URL) and writes a JSON report. The report and every
line this CLI logs redact ``apikey=``/``api_key=`` from any URL.

``summarize`` — renders a canary report as GitHub step-summary markdown and,
with ``--github``, workflow-command annotations. Stdlib only; it reports and
never gates on report problems (exit 0 for a missing or malformed report;
argument or write errors exit non-zero).

Usage:
    python3 scripts/check_provider_contracts.py check
    python3 scripts/check_provider_contracts.py canary [--max-calls N] [--report PATH]
    python3 scripts/check_provider_contracts.py summarize --report PATH
        [--summary-file PATH] [--github]

See ``docs/dev/provider-contracts.md`` for the full contract schema and the
manual fixture-refresh procedure.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

# Import contract (see docs/dev/provider-contracts.md): every importer,
# including this CLI, uses `from scripts.provider_contracts import ...` so
# `python3 scripts/check_provider_contracts.py` and
# `import scripts.check_provider_contracts` from pytest resolve the same
# module object. Insertion is idempotent.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.provider_contracts import (  # noqa: E402
    Contract,
    ContractLoadError,
    load_contracts,
    redact_url,
    validate_contract_file,
    validate_rows,
)

FetchFn = Callable[[str, dict], "tuple[int, Any]"]


def _load_skill_ids(root: Path) -> list[str]:
    """Read ``skills-index.yaml`` top-level skill ids (owners must exist there)."""
    import yaml

    index_path = root / "skills-index.yaml"
    if not index_path.is_file():
        return []
    data = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    return [s["id"] for s in data.get("skills", []) if isinstance(s, dict) and "id" in s]


def cmd_check(args: argparse.Namespace) -> int:
    try:
        contracts = load_contracts(_REPO_ROOT)
    except ContractLoadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not contracts:
        print(
            "ERROR: no provider contracts found under config/provider-contracts/", file=sys.stderr
        )
        return 1

    skill_ids = _load_skill_ids(_REPO_ROOT)
    errors: list[str] = []
    for name in sorted(contracts):
        errors.extend(validate_contract_file(contracts[name], skill_ids))

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print(f"OK: {len(contracts)} provider contract(s) validated")
    return 0


def _build_requests_fetch(api_key: str) -> FetchFn:
    """Return a ``fetch(path, query) -> (status, json)`` backed by real ``requests``.

    Lazy-imported: this is the only place in the whole module tree that
    imports ``requests``, and it only runs inside ``canary``.
    """
    import requests

    def fetch(path: str, query: dict) -> tuple[int, Any]:
        url = f"https://financialmodelingprep.com{path}"
        params = dict(query)
        params["apikey"] = api_key  # query-param auth; never string-formatted into url
        try:
            response = requests.get(url, params=params, timeout=30)
        except requests.exceptions.RequestException as exc:
            # A requests exception message can embed the full request URL
            # (apikey included, e.g. a ConnectionError repr); redact it before
            # it ever reaches the report or stderr.
            return (-1, {"error": redact_url(str(exc))})
        try:
            payload = response.json()
        except ValueError:
            payload = None
        return (response.status_code, payload)

    return fetch


def run_canary(contracts: dict[str, Contract], fetch: FetchFn) -> dict[str, Any]:
    """Run one probe per contract via the injectable ``fetch`` and score anomalies."""
    results: dict[str, Any] = {}
    for name in sorted(contracts):
        contract = contracts[name]
        status, data = fetch(contract.endpoint_path, dict(contract.query))
        row_validation = validate_rows(contract, data)
        if data is None:
            rows = 0
        elif isinstance(data, list):
            rows = len(data)
        else:
            rows = 1
        anomalies = [a.as_dict() for a in row_validation.fatal_anomalies]
        if status != 200:
            anomalies.append({"code": f"http_status:{status}", "severity": "fatal"})
        results[name] = {
            "status": status,
            "rows": rows,
            "anomalies": anomalies,
            "deprecations": [a.as_dict() for a in row_validation.deprecations],
            "ok": row_validation.ok and status == 200,
        }
    return results


def _default_report_path() -> Path:
    return _REPO_ROOT / "reports" / f"fmp_canary_{date.today().isoformat()}.json"


def cmd_canary(args: argparse.Namespace) -> int:
    try:
        contracts = load_contracts(_REPO_ROOT)
    except ContractLoadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not contracts:
        print(
            "ERROR: no provider contracts found under config/provider-contracts/", file=sys.stderr
        )
        return 1

    # Default budget is exactly the number of loaded contracts (one call per
    # contract, no slack) — only an explicit --max-calls lower than that
    # refuses to start.
    max_calls = args.max_calls if args.max_calls is not None else len(contracts)
    if len(contracts) > max_calls:
        print(
            f"ERROR: --max-calls {max_calls} is less than the number of contracts "
            f"({len(contracts)}); refusing to start",
            file=sys.stderr,
        )
        return 1

    api_key = os.environ.get("FMP_API_KEY", "")
    if not api_key:
        print("ERROR: FMP_API_KEY environment variable is not set", file=sys.stderr)
        return 1

    fetch = _build_requests_fetch(api_key)
    results = run_canary(contracts, fetch)
    all_ok = all(entry["ok"] for entry in results.values())

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "budget": {"max": max_calls, "used": len(results)},
        "ok": all_ok,
        "contracts": results,
    }

    report_path = Path(args.report) if args.report else _default_report_path()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote canary report to {redact_url(str(report_path))}")

    for name, entry in sorted(results.items()):
        status_word = "OK" if entry["ok"] else "ANOMALY"
        print(f"{name}: {status_word} (status={entry['status']}, rows={entry['rows']})")
        for anomaly in entry["anomalies"]:
            print(f"  fatal: {anomaly['code']}")
        for anomaly in entry["deprecations"]:
            print(f"  deprecation: {anomaly['code']}")

    return 0 if all_ok else 1


# --- summarize ------------------------------------------------------------

_ANNOTATION_CAP = 10  # GitHub shows at most 10 annotations per type per step
_ERROR_TITLE = "FMP contract anomaly"
_WARNING_TITLE = "FMP contract deprecation"
_NO_REPORT_TITLE = "FMP canary report missing"
_NO_REPORT_MESSAGE = (
    "No canary report was produced; the canary step did not complete. See the job log."
)


def load_report(path: Path) -> dict[str, Any] | None:
    """Return the parsed report, or ``None`` if it is missing, unreadable, or not an object."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _clean(value: Any) -> str:
    return redact_url(str(value))


def _escape_data(text: str) -> str:
    """Escape a workflow-command message (``%`` must be replaced first)."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text: str) -> str:
    return _escape_data(text).replace(":", "%3A").replace(",", "%2C")


def _cell(value: Any) -> str:
    text = _clean(value).replace("\r", " ").replace("\n", " ")
    return text.replace("|", "\\|")


def _codes(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [_clean(i.get("code", "?")) for i in items if isinstance(i, dict)]


def _contract_entries(report: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    contracts = report.get("contracts")
    if not isinstance(contracts, dict):
        return []
    return [(str(n), e) for n, e in sorted(contracts.items()) if isinstance(e, dict)]


def render_summary(report: dict[str, Any] | None) -> str:
    """Render a canary report as markdown for ``$GITHUB_STEP_SUMMARY``."""
    if report is None:
        return f"## FMP contract canary\n\n**{_NO_REPORT_MESSAGE}**\n"

    entries = _contract_entries(report)
    all_ok = bool(report.get("ok")) and all(e.get("ok") for _, e in entries)
    budget = report.get("budget") if isinstance(report.get("budget"), dict) else {}
    lines = [
        f"## FMP contract canary: {'OK' if all_ok else 'ANOMALIES'}",
        "",
        f"Generated at {_cell(report.get('generated_at', 'unknown'))}. "
        f"Budget used {_cell(budget.get('used', '?'))}/{_cell(budget.get('max', '?'))}.",
        "",
        "| Contract | HTTP | Rows | Fatal anomalies | Deprecations | OK |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name, entry in entries:
        fatal = ", ".join(_codes(entry.get("anomalies")))
        if not fatal and entry.get("ok") is False:
            fatal = "not ok (no anomaly codes recorded)"
        fatal = fatal or "-"
        deprecated = ", ".join(_codes(entry.get("deprecations"))) or "-"
        lines.append(
            f"| {_cell(name)} | {_cell(entry.get('status', '?'))} | "
            f"{_cell(entry.get('rows', '?'))} | {_cell(fatal)} | {_cell(deprecated)} | "
            f"{'yes' if entry.get('ok') else 'no'} |"
        )
    flagged = any(_codes(e.get("anomalies")) or e.get("ok") is False for _, e in entries)
    if report.get("ok") is False and not flagged:
        lines += ["", "Report-level ok is false but no contract entry is flagged."]
    return "\n".join(lines) + "\n"


def _capped(severity: str, title: str, messages: list[str]) -> list[str]:
    """Format messages as annotations, aggregating overflow into one ``+N more``."""
    if len(messages) > _ANNOTATION_CAP:
        keep = _ANNOTATION_CAP - 1
        messages = messages[:keep] + [f"+{len(messages) - keep} more (see the step summary)"]
    prefix = f"::{severity} title={_escape_property(title)}::"
    return [prefix + _escape_data(m) for m in messages]


def annotations(report: dict[str, Any] | None) -> list[str]:
    """Workflow-command lines: errors for fatal anomalies, warnings for deprecations."""
    if report is None:
        return _capped("error", _NO_REPORT_TITLE, [_NO_REPORT_MESSAGE])
    errors: list[str] = []
    warnings: list[str] = []
    for name, entry in _contract_entries(report):
        fatal = _codes(entry.get("anomalies"))
        if fatal:
            errors.append(f"{_clean(name)}: {', '.join(fatal)}")
        elif entry.get("ok") is False:
            errors.append(f"{_clean(name)}: not ok")
        deprecated = _codes(entry.get("deprecations"))
        if deprecated:
            warnings.append(f"{_clean(name)}: {', '.join(deprecated)}")
    if report.get("ok") is False and not errors:
        errors.append("report-level ok is false but no contract entry is flagged")
    return _capped("error", _ERROR_TITLE, errors) + _capped("warning", _WARNING_TITLE, warnings)


def cmd_summarize(args: argparse.Namespace) -> int:
    report = load_report(Path(args.report))
    markdown = render_summary(report)
    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as handle:
            handle.write(markdown)
    else:
        print(markdown, end="")
    if args.github:
        for line in annotations(report):
            print(line)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    check_parser = sub.add_parser("check", help="offline: validate contract files and fixtures")
    check_parser.set_defaults(func=cmd_check)

    canary_parser = sub.add_parser("canary", help="live: probe FMP and score anomalies")
    canary_parser.add_argument(
        "--max-calls",
        type=int,
        default=None,
        help=(
            "refuse to start if more contracts than this would be probed "
            "(default: the number of loaded contracts)"
        ),
    )
    canary_parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="report output path (default reports/fmp_canary_<YYYY-MM-DD>.json)",
    )
    canary_parser.set_defaults(func=cmd_canary)

    summarize_parser = sub.add_parser(
        "summarize", help="render a canary report as step-summary markdown (never gates)"
    )
    summarize_parser.add_argument("--report", type=str, required=True, help="canary report path")
    summarize_parser.add_argument(
        "--summary-file",
        type=str,
        default=None,
        help="append markdown here (e.g. $GITHUB_STEP_SUMMARY); default: stdout",
    )
    summarize_parser.add_argument(
        "--github",
        action="store_true",
        help="also print ::error/::warning workflow annotations to stdout",
    )
    summarize_parser.set_defaults(func=cmd_summarize)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
