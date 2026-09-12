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

Usage:
    python3 scripts/check_provider_contracts.py check
    python3 scripts/check_provider_contracts.py canary [--max-calls N] [--report PATH]

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
        results[name] = {
            "status": status,
            "rows": rows,
            "anomalies": [a.as_dict() for a in row_validation.fatal_anomalies],
            "deprecations": [a.as_dict() for a in row_validation.deprecations],
            "ok": row_validation.ok,
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
