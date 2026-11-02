#!/usr/bin/env python3
"""CLI for provider response contracts: FMP JSON and public CSVs (Issue #332).

Subcommands:

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

``health`` — stdlib-only operational gate for complete probe evidence and at
least one nonempty HTTP 200 response. Contract drift remains report-only.

Usage:
    python3 scripts/check_provider_contracts.py check
    python3 scripts/check_provider_contracts.py canary [--provider {fmp,trader-monty,all}]
        [--max-calls N] [--report PATH]
    python3 scripts/check_provider_contracts.py summarize --report PATH
        [--summary-file PATH] [--github]
    python3 scripts/check_provider_contracts.py health --report PATH
        --probe-outcome {success,failure} --probe-exit-code {0,1}

See ``docs/dev/provider-contracts.md`` for the full contract schema and the
manual fixture-refresh procedure.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import sys
from dataclasses import dataclass, field
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
    DEPRECATION,
    FATAL,
    Anomaly,
    Contract,
    ContractLoadError,
    RowValidation,
    load_contracts,
    parse_csv_rows,
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


@dataclass
class FetchResult:
    """Outcome of one provider probe.

    ``rows`` is ``None`` when no body could be used (transport error, oversized
    or undecodable body, non-200 response). ``extra_anomalies`` carries
    fetch-level FATAL anomalies (``transport_error``, ``body_too_large:<n>``,
    ``decode_error``, ``extra_cells``) that ``validate_rows`` cannot see.
    """

    status: int
    rows: Any
    extra_anomalies: list[Anomaly] = field(default_factory=list)


ProviderFetch = Callable[[Contract], FetchResult]

_FMP_PROVIDER = "fmp"
_CSV_TIMEOUT_SECONDS = 30
_CSV_CHUNK_BYTES = 64 * 1024


def _legacy_fmp_adapter(fetch: FetchFn) -> ProviderFetch:
    """Wrap a legacy ``fetch(path, query) -> (status, json)`` as a provider fetch."""

    def adapted(contract: Contract) -> FetchResult:
        status, data = fetch(contract.endpoint_path, dict(contract.query))
        return FetchResult(status, data, [])

    return adapted


def _build_public_csv_fetch() -> ProviderFetch:
    """Return a ``fetch(contract) -> FetchResult`` for keyless public CSVs.

    One GET to ``contract.url`` with no credentials and redirects disabled
    (a redirect off the allowlisted host must surface as ``http_status``, not
    be followed). The body is streamed and capped at ``max_bytes`` of
    *decompressed* bytes, then decoded as ``utf-8-sig``. ``requests`` is
    imported lazily, like ``_build_requests_fetch``.
    """
    import requests

    def fetch(contract: Contract) -> FetchResult:
        limit = contract.effective_max_bytes
        response = None
        try:
            response = requests.get(
                contract.url,
                timeout=_CSV_TIMEOUT_SECONDS,
                allow_redirects=False,
                stream=True,
            )
            status = response.status_code
            if status != 200:
                return FetchResult(status, None, [])
            buffer = bytearray()
            for chunk in response.iter_content(chunk_size=_CSV_CHUNK_BYTES):
                buffer.extend(chunk)
                if len(buffer) > limit:
                    return FetchResult(200, None, [Anomaly(f"body_too_large:{limit}", FATAL)])
        except requests.exceptions.RequestException as exc:
            print(
                f"transport error probing {contract.endpoint}: {redact_url(str(exc))}",
                file=sys.stderr,
            )
            return FetchResult(-1, None, [Anomaly("transport_error", FATAL)])
        finally:
            if response is not None:
                response.close()
        try:
            text = bytes(buffer).decode("utf-8-sig")
        except UnicodeDecodeError:
            return FetchResult(200, None, [Anomaly("decode_error", FATAL)])
        try:
            rows, parse_anomalies = parse_csv_rows(text)
        except csv.Error:
            # NUL byte or a field over the csv size limit: report this contract
            # as drift instead of aborting the whole canary.
            return FetchResult(200, None, [Anomaly("parse_error", FATAL)])
        return FetchResult(200, rows, parse_anomalies)

    return fetch


def _resolve_fetchers(
    contracts: dict[str, Contract], fetch: FetchFn | dict[str, ProviderFetch]
) -> dict[str, ProviderFetch]:
    """Normalize ``run_canary``'s ``fetch`` argument into a provider -> fetch dict.

    A bare callable is the legacy FMP ``(path, query)`` fetch and is only valid
    when every selected contract is an FMP/json contract.
    """
    if isinstance(fetch, dict):
        return fetch
    for name, contract in contracts.items():
        if contract.provider != _FMP_PROVIDER or contract.format != "json":
            raise TypeError(
                f"a bare (path, query) fetch only supports fmp json contracts; "
                f"'{name}' is {contract.provider}/{contract.format} (pass a provider dict)"
            )
    return {_FMP_PROVIDER: _legacy_fmp_adapter(fetch)}


def run_canary(
    contracts: dict[str, Contract], fetch: FetchFn | dict[str, ProviderFetch]
) -> dict[str, Any]:
    """Run one probe per contract and score anomalies.

    ``fetch`` is either a dict ``{provider: fetch(contract) -> FetchResult}`` or
    a bare legacy FMP callable ``fetch(path, query) -> (status, json)``.
    Anomalies are reported deduplicated as ``{code, severity, count}``.
    """
    fetchers = _resolve_fetchers(contracts, fetch)
    results: dict[str, Any] = {}
    for name in sorted(contracts):
        contract = contracts[name]
        if contract.provider not in fetchers:
            raise ValueError(f"no fetcher for provider '{contract.provider}' ('{name}')")
        fetched = fetchers[contract.provider](contract)
        data = fetched.rows
        # CSV: with no rows (transport/size/decode failure, non-200) there is
        # nothing to validate; a spurious empty_response would bury the cause.
        if contract.format == "csv" and data is None:
            validation = RowValidation()
        else:
            validation = validate_rows(contract, data)
        merged = RowValidation(list(fetched.extra_anomalies) + validation.anomalies)
        if data is None:
            rows = 0
        elif isinstance(data, list):
            rows = len(data)
        else:
            rows = 1
        anomalies = merged.summarized(FATAL)
        # A CSV transport_error already explains status -1; do not add http_status:-1.
        if fetched.status != 200 and not any(a["code"] == "transport_error" for a in anomalies):
            anomalies.append(
                {"code": f"http_status:{fetched.status}", "severity": FATAL, "count": 1}
            )
        results[name] = {
            "status": fetched.status,
            "rows": rows,
            "anomalies": anomalies,
            "deprecations": merged.summarized(DEPRECATION),
            "ok": merged.ok and fetched.status == 200,
        }
    return results


def _default_report_path(provider: str = _FMP_PROVIDER) -> Path:
    return _REPO_ROOT / "reports" / f"{provider}_canary_{date.today().isoformat()}.json"


_PROVIDER_CHOICES = ("fmp", "trader-monty", "all")


def _select_contracts(contracts: dict[str, Contract], provider: str) -> dict[str, Contract]:
    if provider == "all":
        return dict(contracts)
    return {name: c for name, c in contracts.items() if c.provider == provider}


def _count_suffix(item: dict[str, Any]) -> str:
    count = item.get("count")
    return f" x{count}" if isinstance(count, int) and count > 1 else ""


def cmd_canary(args: argparse.Namespace) -> int:
    try:
        all_contracts = load_contracts(_REPO_ROOT)
    except ContractLoadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    provider = args.provider
    contracts = _select_contracts(all_contracts, provider)
    if not contracts:
        print(
            f"ERROR: no provider contracts found for provider '{provider}' under "
            "config/provider-contracts/",
            file=sys.stderr,
        )
        return 1

    # Default budget is exactly the number of selected contracts (one call per
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

    fetchers: dict[str, ProviderFetch] = {}
    if any(c.provider == _FMP_PROVIDER for c in contracts.values()):
        api_key = os.environ.get("FMP_API_KEY", "")
        if not api_key:
            print("ERROR: FMP_API_KEY environment variable is not set", file=sys.stderr)
            return 1
        fetchers[_FMP_PROVIDER] = _legacy_fmp_adapter(_build_requests_fetch(api_key))
    public_fetch = None
    for contract in contracts.values():
        if contract.provider != _FMP_PROVIDER:
            if public_fetch is None:
                public_fetch = _build_public_csv_fetch()
            fetchers[contract.provider] = public_fetch

    results = run_canary(contracts, fetchers)
    all_ok = all(entry["ok"] for entry in results.values())

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "budget": {"max": max_calls, "used": len(results)},
        "ok": all_ok,
        "contracts": results,
    }

    report_path = Path(args.report) if args.report else _default_report_path(provider)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote canary report to {redact_url(str(report_path))}")

    for name, entry in sorted(results.items()):
        status_word = "OK" if entry["ok"] else "ANOMALY"
        print(f"{name}: {status_word} (status={entry['status']}, rows={entry['rows']})")
        for anomaly in entry["anomalies"]:
            print(f"  fatal: {anomaly['code']}{_count_suffix(anomaly)}")
        for anomaly in entry["deprecations"]:
            print(f"  deprecation: {anomaly['code']}{_count_suffix(anomaly)}")

    return 0 if all_ok else 1


# --- summarize ------------------------------------------------------------

_ANNOTATION_CAP = 10  # GitHub shows at most 10 annotations per type per step
_FMP_TITLES = {
    "heading": "FMP contract canary",
    "error": "FMP contract anomaly",
    "warning": "FMP contract deprecation",
    "missing": "FMP canary report missing",
}
_PUBLIC_TITLES = {
    "heading": "Public CSV contract canary",
    "error": "Public CSV contract anomaly",
    "warning": "Public CSV contract deprecation",
    "missing": "Public CSV canary report missing",
}
_NEUTRAL_TITLES = {
    "heading": "Provider contract canary",
    "error": "Provider contract anomaly",
    "warning": "Provider contract deprecation",
    "missing": "Provider canary report missing",
}
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


def _titles(report: dict[str, Any] | None, provider: str | None) -> dict[str, str]:
    """Pick FMP, public-CSV or neutral titles; a report's own ``provider`` wins, absent means FMP."""
    reported = report.get("provider") if isinstance(report, dict) else None
    chosen = reported if isinstance(reported, str) and reported else provider
    if chosen in (None, "", _FMP_PROVIDER):
        return _FMP_TITLES
    if chosen == "all":
        return _NEUTRAL_TITLES
    return _PUBLIC_TITLES


def _clean(value: Any) -> str:
    return redact_url(str(value))


def _escape_data(text: str) -> str:
    """Escape a workflow-command message (``%`` must be replaced first)."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text: str) -> str:
    return _escape_data(text).replace(":", "%3A").replace(",", "%2C")


def _cell(value: Any) -> str:
    text = _clean(value).replace("\r", " ").replace("\n", " ")
    return html.escape(text, quote=False).replace("|", "\\|")


def _codes(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [_clean(i.get("code", "?")) for i in items if isinstance(i, dict)]


def _counted_codes(items: Any) -> list[str]:
    """Like ``_codes`` but renders ``code \u00d7count`` when an entry repeated."""
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        code = _clean(item.get("code", "?"))
        count = item.get("count")
        out.append(f"{code} \u00d7{count}" if isinstance(count, int) and count > 1 else code)
    return out


def _contract_entries(report: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    contracts = report.get("contracts")
    if not isinstance(contracts, dict):
        return []
    return [(str(n), e) for n, e in sorted(contracts.items()) if isinstance(e, dict)]


def render_summary(report: dict[str, Any] | None, provider: str | None = None) -> str:
    """Render a canary report as markdown for ``$GITHUB_STEP_SUMMARY``."""
    titles = _titles(report, provider)
    if report is None:
        return f"## {titles['heading']}\n\n**{_NO_REPORT_MESSAGE}**\n"

    entries = _contract_entries(report)
    all_ok = bool(entries) and bool(report.get("ok")) and all(e.get("ok") for _, e in entries)
    budget = report.get("budget") if isinstance(report.get("budget"), dict) else {}
    lines = [
        f"## {titles['heading']}: {'OK' if all_ok else 'ANOMALIES'}",
        "",
        f"Generated at {_cell(report.get('generated_at', 'unknown'))}. "
        f"Budget used {_cell(budget.get('used', '?'))}/{_cell(budget.get('max', '?'))}.",
        "",
        "| Contract | HTTP | Rows | Fatal anomalies | Deprecations | OK |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if not entries:
        lines.insert(2, "No contracts found in the canary report.\n")
    for name, entry in entries:
        fatal = ", ".join(_counted_codes(entry.get("anomalies")))
        if not fatal and entry.get("ok") is False:
            fatal = "not ok (no anomaly codes recorded)"
        fatal = fatal or "-"
        deprecated = ", ".join(_counted_codes(entry.get("deprecations"))) or "-"
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


def annotations(report: dict[str, Any] | None, provider: str | None = None) -> list[str]:
    """Workflow-command lines: errors for fatal anomalies, warnings for deprecations."""
    titles = _titles(report, provider)
    if report is None:
        return _capped("error", titles["missing"], [_NO_REPORT_MESSAGE])
    if not _contract_entries(report):
        title = titles["missing"].replace("report missing", "report has no contracts")
        return _capped("error", title, ["No contracts found in the canary report."])
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
    return _capped("error", titles["error"], errors) + _capped(
        "warning", titles["warning"], warnings
    )


def cmd_summarize(args: argparse.Namespace) -> int:
    report = load_report(Path(args.report))
    markdown = render_summary(report, args.provider)
    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as handle:
            handle.write(markdown)
    else:
        print(markdown, end="")
    if args.github:
        for line in annotations(report, args.provider):
            print(line)
    return 0


def _integer(value: Any, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def health_errors(
    report: dict | None,
    expected: set[str],
    provider: str,
    probe_outcome: str,
    probe_exit_code: int,
) -> list[str]:
    """Validate operational evidence, independently of contract field drift.

    Nonempty HTTP 200 responses are usable for diagnosing drift, including
    field/type/nullability anomalies. This does not certify market-data quality.
    Diagnostics intentionally contain no raw report values or exception text.
    """
    if not isinstance(report, dict):
        return ["Canary report missing, unreadable, or malformed."]
    if report.get("provider", "fmp") != provider:
        return ["Canary report provider does not match the selected provider."]
    try:
        timestamp = datetime.fromisoformat(report["generated_at"].replace("Z", "+00:00"))
        if timestamp.utcoffset() is None:
            raise ValueError("timezone required")
    except (KeyError, AttributeError, TypeError, ValueError):
        return ["Canary report has no valid generation timestamp."]
    entries = report.get("contracts")
    if not expected or not isinstance(entries, dict) or not entries:
        return ["Canary report has no contracts."]
    if set(entries) != expected:
        return ["Canary report contract set is incomplete or unexpected."]
    budget = report.get("budget")
    if (
        not isinstance(budget, dict)
        or not _integer(budget.get("used"), 1)
        or not _integer(budget.get("max"), 1)
        or budget["used"] != len(expected)
        or budget["max"] < budget["used"]
    ):
        return ["Canary report has inconsistent probe budget evidence."]
    usable = False
    for entry in entries.values():
        if not isinstance(entry, dict) or type(entry.get("ok")) is not bool:
            return ["Canary report has a malformed contract entry."]
        status = entry.get("status")
        if not (type(status) is int and (status == -1 or 100 <= status <= 599)):
            return ["Canary report has an invalid HTTP status."]
        if not _integer(entry.get("rows")):
            return ["Canary report has an invalid row count."]
        for evidence_key, severity in (("anomalies", "fatal"), ("deprecations", "deprecation")):
            items = entry.get(evidence_key)
            if not isinstance(items, list) or any(
                not isinstance(item, dict)
                or not isinstance(item.get("code"), str)
                or not item["code"]
                or item.get("severity") != severity
                or not _integer(item.get("count", 1), 1)
                for item in items
            ):
                return ["Canary report has malformed anomaly evidence."]
        if entry["ok"] != (status == 200 and not entry["anomalies"]):
            return ["Canary report contract status contradicts its anomalies."]
        usable |= status == 200 and entry["rows"] > 0
    if type(report.get("ok")) is not bool or report["ok"] != all(
        entry["ok"] for entry in entries.values()
    ):
        return ["Canary report overall status contradicts its contract entries."]
    expected_code = 0 if report["ok"] else 1
    expected_outcome = "success" if expected_code == 0 else "failure"
    if probe_exit_code != expected_code or probe_outcome != expected_outcome:
        return ["Canary probe did not complete with the expected report/exit status."]
    if not usable:
        return ["Canary returned no nonempty HTTP 200 response; no usable probe evidence."]
    return []


def cmd_health(args: argparse.Namespace) -> int:
    try:
        expected = set(_select_contracts(load_contracts(_REPO_ROOT), args.provider))
    except (ContractLoadError, OSError, ValueError):
        errors = ["Cannot load expected provider contracts for the health gate."]
    else:
        errors = health_errors(
            load_report(Path(args.report)),
            expected,
            args.provider,
            args.probe_outcome,
            args.probe_exit_code,
        )
    if errors:
        for line in _capped("error", "Canary infrastructure failure", errors):
            print(line)
        return 1
    print("Canary operational evidence is usable; contract drift remains report-only.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    check_parser = sub.add_parser("check", help="offline: validate contract files and fixtures")
    check_parser.set_defaults(func=cmd_check)

    canary_parser = sub.add_parser(
        "canary", help="live: probe provider endpoints and score anomalies"
    )
    canary_parser.add_argument(
        "--provider",
        choices=_PROVIDER_CHOICES,
        default="fmp",
        help="which provider's contracts to probe (default fmp; fmp needs FMP_API_KEY)",
    )
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
        help="report output path (default reports/<provider>_canary_<YYYY-MM-DD>.json)",
    )
    canary_parser.set_defaults(func=cmd_canary)

    summarize_parser = sub.add_parser(
        "summarize", help="render a canary report as step-summary markdown (never gates)"
    )
    summarize_parser.add_argument("--report", type=str, required=True, help="canary report path")
    summarize_parser.add_argument(
        "--provider",
        choices=_PROVIDER_CHOICES,
        default=None,
        help="provider titles for a missing report (a report's own provider key wins)",
    )
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

    health_parser = sub.add_parser(
        "health", help="gate probe execution and usable response evidence"
    )
    health_parser.add_argument("--report", required=True)
    health_parser.add_argument("--provider", choices=_PROVIDER_CHOICES, default="fmp")
    health_parser.add_argument("--probe-outcome", required=True)
    health_parser.add_argument("--probe-exit-code", required=True, type=int)
    health_parser.set_defaults(func=cmd_health)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
