#!/usr/bin/env python3
"""
COT Contrarian Crowding Screener

Step 1 of Jason Shapiro's COT contrarian process: detect crowded speculative
(large-speculator / "non-commercial") positioning in CFTC futures markets
using the FMP Commitment of Traders (COT) API. Steps 2-5 (news-failure
confirmation, price-action confirmation, entry, exit) are manual and are
documented in references/shapiro-methodology.md for Claude to guide the user
through.

Data source notes (verified live against the FMP stable API, 2026-07):
  - Only the `stable/commitment-of-traders-*` endpoints are used. The legacy
    `api/v4/commitment_of_traders_report*` endpoints return a different,
    snake_case field schema (e.g. `noncomm_positions_long_all`) and, for the
    report endpoint, ignore the from/to range entirely (always return full
    history). Silently falling back to v4 would corrupt field mapping, so no
    v4 fallback is implemented — a stable-endpoint failure is reported to the
    user instead of guessing at a different schema.
  - `stable/commitment-of-traders-report` does NOT truncate wide date ranges
    (verified: a 6.5-year request returned ~340 weekly rows with no
    truncation), so a single request per symbol covers the full lookback
    window; no per-year pagination is needed.
  - `stable/commitment-of-traders-analysis` does not reliably honor the
    requested date range (a 6.5-year request returned only ~13 weeks), so it
    is not used here. All index/classification math is computed locally in
    cot_index.py from the raw report fields instead.
  - The report endpoint does not support comma-separated multi-symbol
    requests (returns an empty list); one API call per symbol is required.
  - COT endpoints require an FMP Premium+ plan; a free-tier key returns 200
    with data as long as the plan is entitled, otherwise 401/403.

Output:
  - JSON: cot_crowding_YYYY-MM-DD.json
  - Markdown: cot_crowding_YYYY-MM-DD.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - environment guard
    requests = None

from cot_index import (
    classify_extreme,
    compute_cot_index,
    compute_net_position,
    compute_oi_normalized_net,
    compute_week_over_week_change,
    sort_dedupe_rows,
)

SKILL_NAME = "cot-contrarian-detector"
SCHEMA_VERSION = "1.0"

from fmp_client import FMPClient  # noqa: E402  (vendored, generated client)

# Curated liquid/representative subset across the 65 markets FMP's COT list
# covers (indices, rates, FX, metals, energy, one crypto future). Verified
# live: all 23 symbols are present in the current commitment-of-traders-list
# response.
CORE_SYMBOLS = [
    "ES", "NQ", "YM", "QR", "VX",
    "ZT", "ZF", "ZN", "ZB",
    "DX", "E6", "J6", "B6", "A6", "D6", "S6",
    "GC", "SI", "HG", "PL",
    "CL", "NG",
    "BT",
]  # fmt: skip

# Extra calendar weeks fetched beyond the requested lookback to absorb
# holiday gaps / occasional missing weekly reports without under-fetching.
BUFFER_WEEKS = 8

# Top N week-over-week net-position swings shown in the report.
TOP_SWINGS = 10

# `requests` exceptions (ConnectionError, Timeout, ...) embed the full
# request URL — including `?apikey=...` — in their str(). Any error string
# built from an exception or a response body must be passed through
# `_redact()` before it can reach stderr, a raised exception, a skip
# `reason`, or a written report.
#
# Pattern-based redaction only catches shapes that carry an "apikey"
# marker (query string, JSON, URL-encoded). It cannot catch a bare key
# with no marker at all — e.g. echoed verbatim into an HTML error page
# body — so `_redact()` also accepts the known `secret` value and strips
# every literal occurrence of it regardless of surrounding syntax. Both
# layers are applied; neither is sufficient alone.
_APIKEY_PATTERNS = (
    # unquoted query-string style, any spacing around '=': apikey=VALUE
    re.compile(r"apikey\s*=\s*[^&\s'\"]+", re.IGNORECASE),
    # JSON-style key/value pair, double- or single-quoted
    re.compile(r'"apikey"\s*:\s*"[^"]*"', re.IGNORECASE),  # pragma: allowlist secret
    re.compile(r"'apikey'\s*:\s*'[^']*'", re.IGNORECASE),  # pragma: allowlist secret
    # URL-encoded '=' (%3D / %3d): apikey%3DVALUE
    re.compile(r"apikey%3d[^&\s'\"]+", re.IGNORECASE),
)


def _redact(text: str | None, secret: str | None = None) -> str | None:
    """Redact the FMP API key from an error/exception string.

    Defense in depth:
    (a) value-based (primary) — if `secret` is known (the client always
        knows its own key), every literal occurrence of it is replaced
        first, regardless of surrounding syntax. This is the only thing
        that catches a bare key with no "apikey" marker at all.
    (b) pattern-based (secondary/backstop) — also strips common
        apikey=/"apikey":/'apikey':/apikey%3D shapes, covering cases
        where the raw secret isn't available at the call site.
    """
    if not text:
        return text
    if secret:
        text = text.replace(secret, "***REDACTED***")
    for pattern in _APIKEY_PATTERNS:
        text = pattern.sub("apikey=***REDACTED***", text)
    return text


def get_api_key(cli_key: str | None) -> str | None:
    """Resolve the FMP API key: --api-key argument takes priority over env."""
    if cli_key:
        return cli_key
    api_key = os.environ.get("FMP_API_KEY")
    if not api_key:
        print("Warning: FMP_API_KEY environment variable not set", file=sys.stderr)
    return api_key


class CotClient(FMPClient):
    """FMP COT client over the vendored generated client (Issue #495).

    Keeps the CLI-facing contract of the former hand-rolled ``CotClient``
    while transport/auth/retry/rate limiting move into the vendored
    ``fmp_client.py``:

    - ``(data, error)`` results via the ``cot_reports`` extension
      (``get_market_list`` raises, ``get_report`` returns the tuple).
    - Header auth (deliberate change from query-param): the apikey never
      appears in a URL; error strings still pass through the script-level
      ``_redact`` (value + pattern layers) before reaching stderr, skip
      reasons, or reports.
    - ``sleep_seconds`` is kept as the former CLI flag and applied by
      overriding ``RATE_LIMIT_DELAY`` on the instance (the generated core
      reads the class constant at call time; the template stays untouched).
    """

    def __init__(self, api_key: str, sleep_seconds: float = 0.25):
        if requests is None:
            print(
                "ERROR: requests library not found. Install with: pip install requests",
                file=sys.stderr,
            )
            sys.exit(1)
        super().__init__(api_key=api_key)
        self.sleep_seconds = sleep_seconds
        self.RATE_LIMIT_DELAY = sleep_seconds

    # Back-compat notes for pinned tests: ``client.session`` and
    # ``client.api_calls_made`` come from the generated client.
    def get_report(self, symbol: str, from_date: str, to_date: str):
        data, error = super().get_report(symbol, from_date, to_date)
        return data, _redact(error, secret=self.api_key)


def parse_symbols_arg(raw: str) -> list[str]:
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def resolve_universe(args: argparse.Namespace, client: CotClient) -> tuple[list[str], str]:
    """Return (symbol list, universe_mode label)."""
    if args.symbols:
        return parse_symbols_arg(args.symbols), "explicit_symbols"
    if args.core:
        return list(CORE_SYMBOLS), "core"
    market_list = client.get_market_list()
    symbols = [row["symbol"] for row in market_list if row.get("symbol")]
    return symbols, "all_markets"


def analyze_market(
    symbol: str,
    rows: list[dict[str, Any]],
    fetch_error: str | None,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Compute crowding metrics for one market, or return a `skipped` entry.

    Never silently drops a market: every symbol in the universe ends up
    either in the analyzed results or in the skipped list with a reason.
    """
    if fetch_error:
        return {
            "symbol": symbol,
            "status": "skipped",
            "reason": f"API fetch failed: {fetch_error}",
            "weeks_available": 0,
        }
    if not rows:
        return {
            "symbol": symbol,
            "status": "skipped",
            "reason": "no data returned by API",
            "weeks_available": 0,
        }

    sorted_rows = sort_dedupe_rows(rows)
    net_series = [compute_net_position(row) for row in sorted_rows]
    weeks_available = len(net_series)

    if weeks_available < args.short_lookback_weeks:
        return {
            "symbol": symbol,
            "status": "skipped",
            "reason": (
                f"insufficient history: {weeks_available}/{args.short_lookback_weeks} "
                "weeks (below short lookback)"
            ),
            "weeks_available": weeks_available,
        }

    cot_index_3y = compute_cot_index(net_series, args.lookback_weeks)
    if cot_index_3y is None:
        if weeks_available < args.lookback_weeks:
            reason = f"insufficient history: {weeks_available}/{args.lookback_weeks} weeks"
        else:
            reason = (
                f"flat net-position window over {args.lookback_weeks} weeks "
                "(max == min, index undefined)"
            )
        return {
            "symbol": symbol,
            "status": "skipped",
            "reason": reason,
            "weeks_available": weeks_available,
        }

    latest = sorted_rows[-1]
    cot_index_short = compute_cot_index(net_series, args.short_lookback_weeks)
    classification = classify_extreme(cot_index_3y, args.threshold_high, args.threshold_low)
    wow_change = compute_week_over_week_change(net_series)

    return {
        "symbol": symbol,
        "status": "ok",
        "name": latest.get("name", symbol),
        "sector": latest.get("sector"),
        "contract_units": latest.get("contractUnits"),
        "data_date": (latest.get("date") or "")[:10],
        "weeks_available": weeks_available,
        "net_position": net_series[-1],
        "open_interest": latest.get("openInterestAll"),
        "oi_normalized_net": compute_oi_normalized_net(latest),
        "cot_index_3y": round(cot_index_3y, 1),
        "cot_index_short": round(cot_index_short, 1) if cot_index_short is not None else None,
        "week_over_week_change": wow_change,
        "pct_oi_long": latest.get("pctOfOiNoncommLongAll"),
        "pct_oi_short": latest.get("pctOfOiNoncommShortAll"),
        "traders_long": latest.get("tradersNoncommLongAll"),
        "traders_short": latest.get("tradersNoncommShortAll"),
        "classification": classification,
        "extremity": round(abs(cot_index_3y - 50.0), 1),
    }


def collect_results(
    args: argparse.Namespace, client: CotClient
) -> tuple[list[dict[str, Any]], list[str], str]:
    """Fetch + analyze every market in the resolved universe.

    Returns (results, universe_symbols, universe_mode). `results` contains
    both "ok" and "skipped" entries — callers must not drop either.
    """
    universe_symbols, universe_mode = resolve_universe(args, client)
    if not universe_symbols:
        raise ValueError("No symbols to process. Check --symbols/--core or the FMP COT list API.")

    as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date()
    from_date = (as_of - timedelta(weeks=args.lookback_weeks + BUFFER_WEEKS)).strftime("%Y-%m-%d")
    to_date = as_of.strftime("%Y-%m-%d")

    results = []
    for idx, symbol in enumerate(universe_symbols, 1):
        print(f"  Fetching COT report: {idx}/{len(universe_symbols)} ({symbol})", flush=True)
        rows, error = client.get_report(symbol, from_date, to_date)
        results.append(analyze_market(symbol, rows, error, args))

    return results, universe_symbols, universe_mode


def resolve_data_date(results: list[dict[str, Any]]) -> str | None:
    """Most common `data_date` among analyzed markets (the consensus report date)."""
    dates = [r["data_date"] for r in results if r.get("status") == "ok" and r.get("data_date")]
    if not dates:
        return None
    counts: dict[str, int] = {}
    for d in dates:
        counts[d] = counts.get(d, 0) + 1
    return max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]


def build_run_context(
    args: argparse.Namespace,
    universe_symbols: list[str],
    universe_mode: str,
    data_date: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "as_of": args.as_of,
        "data_date": data_date,
        "universe_mode": universe_mode,
        "universe_size": len(universe_symbols),
        "params": {
            "lookback_weeks": args.lookback_weeks,
            "short_lookback_weeks": args.short_lookback_weeks,
            "threshold_high": args.threshold_high,
            "threshold_low": args.threshold_low,
        },
    }


def build_data_provenance(
    results: list[dict[str, Any]], run_context: dict[str, Any]
) -> dict[str, Any]:
    """Describe collected COT vintages without asserting historical availability.

    The request cutoff is only a query reference when no markets were analyzed.
    An analyzed row with an unknown vintage must never use that fallback.
    """
    market_dates = {}
    for result in results:
        if result["status"] != "ok":
            continue
        value = result.get("data_date")
        try:
            valid = isinstance(value, str) and date.fromisoformat(value).isoformat() == value
        except ValueError:
            valid = False
        if not valid:
            shown = repr(value)
            if len(shown) > 40:
                shown = shown[:40] + "..."
            raise ValueError(
                f"Analyzed COT market {result.get('symbol')!s} requires a valid "
                f"YYYY-MM-DD data_date, got {shown}"
            )
        # Repeated symbols may return different vintages during one collection.
        # Preserve the oldest observation instead of silently refreshing it.
        symbol = result["symbol"]
        market_dates[symbol] = min(market_dates.get(symbol, value), value)

    return {
        "schema_version": "1.0",
        "provider": "fmp",
        "endpoint": "commitment-of-traders-report",
        "retrieved_at": run_context["retrieved_at"],
        "as_of": (
            min(market_dates.values())
            if market_dates
            else datetime.strptime(run_context["as_of"], "%Y-%m-%d").date().isoformat()
        ),
        "timezone": "America/New_York",
        "adjusted": False,
        "point_in_time": False,
        "survivorship_free": False,
        "corporate_actions_handled": False,
        "as_of_basis": (
            "oldest_analyzed_market_report" if market_dates else "request_cutoff_no_analyzed_data"
        ),
        "market_data_dates": market_dates,
    }


def generate_json_report(
    results: list[dict[str, Any]], run_context: dict[str, Any], output_path: str
) -> None:
    ok_results = sorted(
        (r for r in results if r["status"] == "ok"), key=lambda r: r["extremity"], reverse=True
    )
    skipped = [r for r in results if r["status"] == "skipped"]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "run_context": run_context,
        "data_provenance": build_data_provenance(results, run_context),
        "markets": ok_results,
        "skipped": skipped,
    }
    Path(output_path).write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def _fmt(value: Any, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _fmt_pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.{digits}f}%"


def _market_row_md(r: dict[str, Any]) -> str:
    return (
        f"| {r['symbol']} | {r.get('name', r['symbol'])} | {_fmt(r['cot_index_3y'])} | "
        f"{_fmt(r['cot_index_short'])} | {r['net_position']:,} | "
        f"{_fmt_pct(r['oi_normalized_net'], 2)} | {_fmt(r['pct_oi_long'])} / "
        f"{_fmt(r['pct_oi_short'])} | {_fmt(r['week_over_week_change'], 0)} |"
    )


def generate_markdown_report(
    results: list[dict[str, Any]], run_context: dict[str, Any], output_path: str
) -> None:
    ok_results = sorted(
        (r for r in results if r["status"] == "ok"), key=lambda r: r["extremity"], reverse=True
    )
    skipped = [r for r in results if r["status"] == "skipped"]
    crowded_long = [r for r in ok_results if r["classification"] == "CROWDED_LONG"]
    crowded_short = [r for r in ok_results if r["classification"] == "CROWDED_SHORT"]
    swings = sorted(
        (r for r in ok_results if r.get("week_over_week_change") is not None),
        key=lambda r: abs(r["week_over_week_change"]),
        reverse=True,
    )[:TOP_SWINGS]

    header = ["SYMBOL", "NAME", "INDEX_3Y", "INDEX_26W", "NET_POS", "NET/OI", "%OI L/S", "WoW"]
    table_head = f"| {' | '.join(header)} |"
    table_sep = "|" + "|".join(["---"] * len(header)) + "|"

    lines = [
        "# COT Contrarian Crowding Report",
        "",
        f"Generated at: {run_context['generated_at']}",
        f"As-of date: {run_context['as_of']}",
        f"COT data date: {run_context.get('data_date') or 'n/a'}",
        f"Universe: `{run_context['universe_mode']}` ({run_context['universe_size']} markets)",
        f"Lookback: {run_context['params']['lookback_weeks']}w primary / "
        f"{run_context['params']['short_lookback_weeks']}w short",
        f"Extreme thresholds: high >= {run_context['params']['threshold_high']}, "
        f"low <= {run_context['params']['threshold_low']}",
        "",
        "## Summary",
        "",
        f"- Markets analyzed: {len(ok_results)}",
        f"- Crowded long (fade candidates for SHORT setups): {len(crowded_long)}",
        f"- Crowded short (fade candidates for LONG setups): {len(crowded_short)}",
        f"- Skipped (insufficient/failed data): {len(skipped)}",
        "",
        "## Crowded Long (COT Index >= high threshold)",
        "",
        "Large speculators are near their most net-long extreme of the lookback "
        "window. This is a *candidate* for a contrarian SHORT — proceed to "
        "Shapiro steps 2-5 (news failure, price action, entry, exit) before "
        "trading. Crowdedness alone is not a signal.",
        "",
    ]
    if crowded_long:
        lines += [table_head, table_sep]
        lines += [_market_row_md(r) for r in crowded_long]
    else:
        lines.append("None.")
    lines += [
        "",
        "## Crowded Short (COT Index <= low threshold)",
        "",
        "Large speculators are near their most net-short extreme of the lookback "
        "window. This is a *candidate* for a contrarian LONG — proceed to "
        "Shapiro steps 2-5 before trading.",
        "",
    ]
    if crowded_short:
        lines += [table_head, table_sep]
        lines += [_market_row_md(r) for r in crowded_short]
    else:
        lines.append("None.")

    lines += [
        "",
        "## Full Ranking (by extremity, |COT Index - 50| descending)",
        "",
        table_head,
        table_sep,
    ]
    lines += [_market_row_md(r) for r in ok_results]

    lines += [
        "",
        "## Biggest Week-over-Week Net Position Swings",
        "",
        "| SYMBOL | NAME | WoW CHANGE | NET_POS | CLASSIFICATION |",
        "|---|---|---|---|---|",
    ]
    for r in swings:
        lines.append(
            f"| {r['symbol']} | {r.get('name', r['symbol'])} | "
            f"{_fmt(r['week_over_week_change'], 0)} | {r['net_position']:,} | "
            f"{r['classification']} |"
        )

    lines += ["", "## Skipped Markets", ""]
    if skipped:
        lines += ["| SYMBOL | REASON | WEEKS AVAILABLE |", "|---|---|---|"]
        for r in skipped:
            lines.append(f"| {r['symbol']} | {r['reason']} | {r['weeks_available']} |")
    else:
        lines.append("None — every requested market was analyzed.")

    lines += [
        "",
        "## Methodology",
        "",
        "COT Index = (current net large-speculator position - lookback minimum) / "
        "(lookback maximum - lookback minimum) * 100, computed from the CFTC legacy "
        "report's non-commercial long/short fields. See "
        "`references/cot-index-calculation.md` for the full formula and field "
        "glossary, and `references/shapiro-methodology.md` for the manual steps "
        "(news failure, price action, entry, exit) that must confirm any crowding "
        "signal before it becomes a trade.",
        "",
        "**Disclaimer:** This report is a crowding-detection screen only. It is not "
        "investment advice and is not a standalone entry signal. COT data is "
        "published Fridays ~3:30pm ET with positions as of the prior Tuesday — "
        "always a few days old by the time it is read.",
        "",
    ]

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Screen CFTC COT reports for crowded large-speculator positioning "
        "(Jason Shapiro contrarian process, step 1)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Curated core futures universe (23 markets)
  python screen_cot_crowding.py --core

  # Explicit symbols
  python screen_cot_crowding.py --symbols "ES,GC,CL"

  # Full universe (all markets FMP's COT list covers)
  python screen_cot_crowding.py
        """,
    )
    parser.add_argument("--symbols", help='Comma-separated symbols, e.g. "ES,GC,CL"')
    parser.add_argument(
        "--core", action="store_true", help="Use the curated core futures subset (23 markets)"
    )
    parser.add_argument(
        "--lookback-weeks", type=int, default=156, help="Primary COT Index lookback (default: 156)"
    )
    parser.add_argument(
        "--short-lookback-weeks",
        type=int,
        default=26,
        help="Short-window COT Index lookback for context (default: 26)",
    )
    parser.add_argument(
        "--threshold-high", type=float, default=90.0, help="Crowded-long threshold (default: 90)"
    )
    parser.add_argument(
        "--threshold-low", type=float, default=10.0, help="Crowded-short threshold (default: 10)"
    )
    parser.add_argument(
        "--as-of",
        default=date.today().strftime("%Y-%m-%d"),
        help="Reference date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--output-dir", default="reports/", help="Output directory (default: reports/)"
    )
    parser.add_argument(
        "--sleep-seconds", type=float, default=0.25, help="Delay between API calls (default: 0.25)"
    )
    parser.add_argument(
        "--format",
        choices=["json", "md", "both"],
        default="both",
        help="Output format (default: both)",
    )
    parser.add_argument(
        "--api-key", help="FMP API key (overrides FMP_API_KEY environment variable)"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    print("=" * 72)
    print("COT Contrarian Crowding Screener")
    print("=" * 72)

    api_key = get_api_key(args.api_key)
    if not api_key:
        print(
            "Error: FMP API key is required. Set FMP_API_KEY environment variable or "
            "use --api-key. Note: COT endpoints require an FMP Premium+ plan.",
            file=sys.stderr,
        )
        sys.exit(1)

    client = CotClient(api_key=api_key, sleep_seconds=args.sleep_seconds)

    try:
        results, universe_symbols, universe_mode = collect_results(args, client)
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    data_date = resolve_data_date(results)
    run_context = build_run_context(args, universe_symbols, universe_mode, data_date)

    os.makedirs(args.output_dir, exist_ok=True)
    json_path = os.path.join(args.output_dir, f"cot_crowding_{args.as_of}.json")
    md_path = os.path.join(args.output_dir, f"cot_crowding_{args.as_of}.md")

    try:
        if args.format in ("json", "both"):
            generate_json_report(results, run_context, json_path)
        if args.format in ("md", "both"):
            generate_markdown_report(results, run_context, md_path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    ok_results = [r for r in results if r["status"] == "ok"]
    skipped = [r for r in results if r["status"] == "skipped"]
    crowded = [r for r in ok_results if r["classification"] != "NEUTRAL"]

    print()
    print("Screening complete")
    print(f"  Markets analyzed: {len(ok_results)} (skipped: {len(skipped)})")
    print(f"  API calls made:   {client.api_calls_made}")
    if args.format in ("json", "both"):
        print(f"  JSON Report:      {json_path}")
    if args.format in ("md", "both"):
        print(f"  Markdown Report:  {md_path}")

    if crowded:
        print()
        print("Crowded markets:")
        for r in sorted(crowded, key=lambda r: r["extremity"], reverse=True)[:10]:
            print(
                f"  {r['symbol']:6} {r['classification']:14} "
                f"Index3y: {r['cot_index_3y']:5.1f}  Net: {r['net_position']:>10,}"
            )


if __name__ == "__main__":
    main()
