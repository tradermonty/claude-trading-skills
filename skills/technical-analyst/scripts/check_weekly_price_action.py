#!/usr/bin/env python3
"""
Contrarian Confirmation Mode -- Weekly Price Action Checker

Step 3 of Jason Shapiro's COT contrarian process: confirm price-action
evidence of a reversal in a market already flagged as crowded (steps 1-2:
cot-contrarian-detector, news-reaction-failure-analyzer). This is a
data-driven FALLBACK to the technical-analyst skill's primary chart-image
workflow -- it consumes a COT symbol (mapped) or plain ticker, fetches
weekly-resampled OHLC from FMP with a documented fallback chain, and
produces a fail-closed CONFIRMED / NOT_CONFIRMED / INSUFFICIENT_DATA
verdict using the deterministic detectors implemented in
weekly_price_action.py (weekly key reversal, failed extreme, failed
breakout, continuation veto) plus fractal swing levels for a stop
reference.

Data source notes (verified live against the FMP stable API, 2026-07):
  - `stable/historical-price-eod/full` returns OHLC (date/open/high/low/
    close/volume) -- confirmed for GCUSD, ESUSD, BTCUSD, GBPUSD, and ETF
    proxies QQQ/IEF/UUP. NQUSD returns 402 on this key (same tier
    restriction as the light endpoint) -- the documented futures-to-ETF
    fallback chain (copied verbatim from news-reaction-failure-analyzer's
    PRICE_SOURCE_CHAINS, self-contained per repo convention: no
    cross-skill imports) applies unchanged.
  - Field-name trap (verified, the #245 bug class): the `full` endpoint
    uses `close`; the `light` endpoint uses `price`. This script's
    weekly_price_action.build_sorted_daily_series() accepts either
    defensively.
  - Unlike news-reaction-failure-analyzer, --symbol here is not restricted
    to COT futures symbols: if it isn't a mapped COT symbol,
    PRICE_SOURCE_CHAINS falls through to treating it as a plain FMP price
    ticker directly (e.g. an equity or ETF symbol) -- this skill covers
    stocks, indices, crypto, and forex, not only COT-tracked futures.

Redaction: dual-layer (value-based primary + pattern-family secondary), a
self-contained copy of the proven cot-contrarian-detector /
news-reaction-failure-analyzer pattern -- see `_redact()` below.

Output:
  - JSON: ta_confirmation_<symbol>_<as-of>.json
  - Markdown: ta_confirmation_<symbol>_<as-of>.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - environment guard
    requests = None

from weekly_price_action import (
    EXTREME_LOOKBACK_WEEKS_DEFAULT,
    MIN_WEEKS_DEFAULT,
    SIGNAL_RECENCY_WEEKS_DEFAULT,
    SWING_LOOKBACK_WEEKS_DEFAULT,
    build_sorted_daily_series,
    run_weekly_price_action,
)

SKILL_NAME = "technical-analyst"
SCHEMA_VERSION = "1.0"

STABLE_EOD_URL = "https://financialmodelingprep.com/stable/historical-price-eod/full"

MAX_DETECTOR_AGE_DAYS_DEFAULT = 10

# Extra calendar weeks fetched before --as-of so the extreme-lookback window
# (default 52 weeks), the signal-recency window, and the min-weeks floor all
# have real weekly bars to work with even under holiday-thinned calendars.
# No forward/lookahead fetch is needed here (unlike news-reaction-failure-
# analyzer's event-snapping use case) -- this script is purely historical,
# and --as-of truncation happens before a source counts as successful.
WEEKS_FETCH_BUFFER = 10

# --- Price-source map (self-contained copy of news-reaction-failure-
# analyzer's PRICE_SOURCE_CHAINS, per repo convention: no cross-skill
# imports; see that skill's references/price-source-map.md for the full
# per-market probe results this was verified against, 2026-07).
# {cot_symbol: [(price_symbol, kind, invert), ...]} -- tried in order; a
# source fails on HTTP error OR rows == 0; first success wins.
PRICE_SOURCE_CHAINS: dict[str, list[tuple[str, str, bool]]] = {
    "ES": [("ESUSD", "futures", False)],
    "NQ": [("NQUSD", "futures", False), ("QQQ", "etf", False)],
    "YM": [("YMUSD", "futures", False), ("DIA", "etf", False)],
    "QR": [("RTYUSD", "futures", False), ("IWM", "etf", False)],
    "VX": [("VXUSD", "futures", False)],  # 200/0 rows on this key -> no_price_source
    "GC": [("GCUSD", "futures", False)],
    "SI": [("SIUSD", "futures", False)],
    "HG": [("HGUSD", "futures", False), ("CPER", "etf", False)],
    "PL": [("PLUSD", "futures", False), ("PPLT", "etf", False)],
    "PA": [("PAUSD", "futures", False), ("PALL", "etf", False)],
    "CL": [("CLUSD", "futures", False), ("BZUSD", "futures", False), ("USO", "etf", False)],
    "NG": [("NGUSD", "futures", False), ("UNG", "etf", False)],
    "RB": [("RBUSD", "futures", False), ("UGA", "etf", False)],
    "HO": [("HOUSD", "futures", False)],  # no proxy -> no_price_source
    "ZT": [("ZTUSD", "futures", False), ("SHY", "etf", False)],
    "ZF": [("ZFUSD", "futures", False), ("IEI", "etf", False)],
    "ZN": [("ZNUSD", "futures", False), ("IEF", "etf", False)],
    "ZB": [("ZBUSD", "futures", False), ("TLT", "etf", False)],
    "ZQ": [("ZQUSD", "futures", False)],  # no proxy -> no_price_source
    "DX": [("DXUSD", "futures", False), ("UUP", "etf", False)],
    "B6": [("GBPUSD", "futures", False)],
    "E6": [("EURUSD", "futures", False)],
    "J6": [("JPYUSD", "futures", False)],
    "S6": [("CHFUSD", "futures", False)],
    "D6": [("CADUSD", "futures", False)],
    "A6": [("AUDUSD", "futures", False)],
    "N6": [("NZDUSD", "futures", False)],
    "BT": [("BTCUSD", "futures", False)],
    "ZC": [("ZCUSD", "futures", False)],
    "ZS": [("ZSUSD", "futures", False)],
    "ZM": [("ZMUSD", "futures", False)],
    "ZL": [("ZLUSD", "futures", False)],
    "ZW": [("ZWUSD", "futures", False)],
}


# --- Redaction (self-contained copy of the cot-contrarian-detector /
# news-reaction-failure-analyzer pattern)
#
# `requests` exceptions embed the full request URL -- including `?apikey=...`
# -- in their str(). Pattern-based redaction alone only catches shapes with
# an "apikey" marker; value-based redaction (passing the known `secret`)
# also catches a bare key with no marker at all. Both layers are applied;
# neither is sufficient alone.
_APIKEY_PATTERNS = (
    re.compile(r"apikey\s*=\s*[^&\s'\"]+", re.IGNORECASE),
    re.compile(r'"apikey"\s*:\s*"[^"]*"', re.IGNORECASE),
    re.compile(r"'apikey'\s*:\s*'[^']*'", re.IGNORECASE),
    re.compile(r"apikey%3d[^&\s'\"]+", re.IGNORECASE),
)


def _redact(text: str | None, secret: str | None = None) -> str | None:
    """Redact the FMP API key from an error/exception string."""
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


def _request_with_backoff(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    max_retries: int = 4,
    base_delay: float = 1.0,
) -> tuple[Any, str | None]:
    """GET JSON with exponential backoff retry on 429 / 5xx. Non-retryable
    4xx (401/402/403/404/...) fail immediately -- a 402 is expected/routine
    here (advances the fallback chain), not something to retry."""
    secret = params.get("apikey") if isinstance(params, dict) else None
    delay = base_delay
    error = "unknown error"
    for attempt in range(max_retries + 1):
        try:
            response = session.get(url, params=params, timeout=30)
        except requests.exceptions.RequestException as exc:
            error = _redact(f"request exception: {exc}", secret=secret)
        else:
            if response.status_code == 200:
                try:
                    return response.json(), None
                except ValueError as exc:
                    error = _redact(f"invalid JSON response: {exc}", secret=secret)
            elif response.status_code == 429 or response.status_code >= 500:
                error = f"HTTP {response.status_code}"
            else:
                return None, _redact(
                    f"HTTP {response.status_code}: {response.text[:200]}", secret=secret
                )

        if attempt < max_retries:
            print(
                f"WARN: {error}; retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})",
                file=sys.stderr,
            )
            time.sleep(delay)
            delay *= 2
    return None, error


class PriceClient:
    """Thin client for FMP's stable full-OHLC EOD price endpoint with rate limiting."""

    def __init__(self, api_key: str, sleep_seconds: float = 0.25):
        if requests is None:
            print(
                "ERROR: requests library not found. Install with: pip install requests",
                file=sys.stderr,
            )
            sys.exit(1)
        self.api_key = api_key
        self.sleep_seconds = sleep_seconds
        self.session = requests.Session()
        self.last_call_time = 0.0
        self.api_calls_made = 0

    def get_eod_rows(
        self, symbol: str, from_date: str, to_date: str
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
        """Fetch daily OHLCV rows for one symbol. Returns (rows, None) on
        success -- rows may be an EMPTY list (a distinct, documented failure
        mode) -- or (None, error) on an HTTP/transport failure."""
        elapsed = time.time() - self.last_call_time
        if elapsed < self.sleep_seconds:
            time.sleep(self.sleep_seconds - elapsed)
        params = {"symbol": symbol, "from": from_date, "to": to_date, "apikey": self.api_key}
        data, error = _request_with_backoff(self.session, STABLE_EOD_URL, params)
        self.last_call_time = time.time()
        self.api_calls_made += 1
        if error:
            return None, error
        return data if isinstance(data, list) else [], None


def fetch_price_series(
    client: PriceClient,
    chain: list[tuple[str, str, bool]],
    from_date: str,
    to_date: str,
    as_of: str,
) -> dict[str, Any]:
    """Try each (price_symbol, kind, invert) in `chain` in order. A source
    fails on HTTP error OR `rows == 0` (some symbols return 200 with an
    empty body rather than an error). First success wins.

    `as_of` is an INFORMATION CUTOFF: any bar dated after it is dropped
    before a source is considered successful -- a source whose rows are
    entirely after `as_of` degrades the same way as "0 rows".

    Returns a dict:
      success: {"error": None, "daily_bars": [...], "price_symbol",
                "source_kind", "proxy_used", "attempts": [...]}
      all fail: {"error": "no_price_source", "daily_bars": [], "price_symbol": None,
                 "attempts": [...]}
    """
    attempts: list[dict[str, Any]] = []
    for price_symbol, kind, invert in chain:
        rows, error = client.get_eod_rows(price_symbol, from_date, to_date)
        if error:
            attempts.append(
                {"price_symbol": price_symbol, "kind": kind, "status": f"error: {error}"}
            )
            continue
        if not rows:
            attempts.append({"price_symbol": price_symbol, "kind": kind, "status": "0 rows"})
            continue
        daily_bars = build_sorted_daily_series(rows)
        daily_bars = [b for b in daily_bars if b["date"] <= as_of]
        if not daily_bars:
            attempts.append({"price_symbol": price_symbol, "kind": kind, "status": "0 rows"})
            continue
        attempts.append({"price_symbol": price_symbol, "kind": kind, "status": "ok"})
        return {
            "error": None,
            "daily_bars": daily_bars,
            "price_symbol": price_symbol,
            "source_kind": kind,
            "proxy_used": kind == "etf",
            "attempts": attempts,
        }
    return {
        "error": "no_price_source",
        "daily_bars": [],
        "price_symbol": None,
        "source_kind": None,
        "proxy_used": False,
        "attempts": attempts,
    }


# --- Detector-json handling (verbatim behavior copy of the #245 hardened
# guards -- markets[]/skipped[]/absent/NEUTRAL; data_date REQUIRED
# non-empty string, no as_of fallback; structurally-malformed JSON never
# crashes) --------------------------------------------------------------


def load_json_file(path: str) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Read and parse a JSON file. Returns (data, None, None) on success, or
    (None, error, reason) on failure, where `reason` is a machine-readable
    tag distinguishing the two ways this can fail closed: `"unreadable"`
    (the file is missing, unreadable, not valid UTF-8, or otherwise can't
    be read as text) vs `"parse_error"` (the file opened and decoded fine
    but isn't valid JSON). Callers use `reason` (not the free-text `error`
    string, which is for logging only) to pick a specific fail-closed
    verdict_reason (P1 regression, user re-review of PR #247: this file
    previously had no reason tag at all, and callers exited 1 with no
    report for BOTH cases instead of failing closed to INSUFFICIENT_DATA
    like every other degraded-input path in this script).

    Catches `(OSError, UnicodeError)`, not `OSError` alone: a readable
    file that isn't valid UTF-8 raises `UnicodeDecodeError`, which is a
    `ValueError`/`UnicodeError` subclass, NOT an `OSError` -- it used to
    escape this function entirely and crash with a traceback (residual P1,
    user re-review round 2). `MemoryError` and other unrelated exceptions
    are deliberately left uncaught -- those aren't "this input is bad"
    conditions."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return None, f"cannot read {path}: {exc}", "unreadable"
    try:
        return json.loads(text), None, None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON in {path}: {exc}", "parse_error"


def resolve_direction_from_detector(
    detector_data: Any,
    symbol: str,
    as_of: str,
    max_age_days: int,
) -> tuple[str | None, str | None, dict[str, Any]]:
    """Implements the CLI's --detector-json lookup algorithm, copied
    verbatim in behavior from news-reaction-failure-analyzer (#245):

    (a) symbol not in markets[], or present in skipped[] -> refuse with
        reason `detector_missing_symbol`.
    (b) classification == NEUTRAL -> refuse with reason `not_crowded`
        (fail-closed; only an explicit --direction overrides this).
    (c) detector run_context.data_date missing/empty, not a string,
        unparsable, or dated AFTER --as-of -> reason
        `detector_missing_data_date` / `detector_invalid_data_date` /
        `detector_future_data_date` respectively (all fail-closed).
        `data_date` is REQUIRED: run_context.as_of is the RUN date, not
        the DATA vintage, and never substitutes for a missing data_date.
        Older than --max-detector-age-days vs --as-of -> reason
        `detector_json_stale`.

    `detector_data` is untrusted, parsed JSON: valid JSON but the wrong
    shape must never crash -- it degrades to `malformed_detector_json`
    (top-level) or to treating the bad field as absent (per-field).

    Returns (direction, refusal_reason, detector_context). `direction` is
    None whenever `refusal_reason` is set.
    """
    if not isinstance(detector_data, dict):
        return None, "malformed_detector_json", {}

    run_context = detector_data.get("run_context")
    if not isinstance(run_context, dict):
        run_context = {}
    data_date = run_context.get("data_date")
    ctx = {"run_context": run_context, "data_date": data_date}

    markets_raw = detector_data.get("markets")
    markets = markets_raw if isinstance(markets_raw, list) else []
    skipped_raw = detector_data.get("skipped")
    skipped_list = skipped_raw if isinstance(skipped_raw, list) else []
    skipped_symbols = {s.get("symbol") for s in skipped_list if isinstance(s, dict)}
    market_row = next(
        (m for m in markets if isinstance(m, dict) and m.get("symbol") == symbol), None
    )

    if market_row is None or symbol in skipped_symbols:
        return None, "detector_missing_symbol", ctx

    if data_date is None or data_date == "":
        return None, "detector_missing_data_date", ctx
    if not isinstance(data_date, str):
        return None, "detector_invalid_data_date", ctx
    try:
        as_of_dt = datetime.strptime(as_of, "%Y-%m-%d").date()
        data_dt = datetime.strptime(data_date[:10], "%Y-%m-%d").date()
    except ValueError:
        return None, "detector_invalid_data_date", ctx
    age_days = (as_of_dt - data_dt).days
    ctx["detector_age_days"] = age_days
    if age_days < 0:
        return None, "detector_future_data_date", ctx
    if age_days > max_age_days:
        return None, "detector_json_stale", ctx

    classification = market_row.get("classification")
    if classification == "NEUTRAL":
        return None, "not_crowded", ctx
    if classification not in ("CROWDED_LONG", "CROWDED_SHORT"):
        return None, "detector_missing_symbol", ctx
    return classification, None, ctx


# --- Report assembly -----------------------------------------------------


def build_run_context(
    price_symbol: str | None,
    price_source: str | None,
    proxy_used: bool,
    as_of: str,
    swing_lookback_weeks: int,
    extreme_lookback_weeks: int,
    signal_recency_weeks: int,
    min_weeks: int,
    detector_json: str | None,
    detector_age_days: int | None,
) -> dict[str, Any]:
    return {
        "price_symbol": price_symbol,
        "price_source": price_source,
        "proxy_used": proxy_used,
        "as_of": as_of,
        "lookbacks": {
            "swing_lookback_weeks": swing_lookback_weeks,
            "extreme_lookback_weeks": extreme_lookback_weeks,
        },
        "recency": {"signal_recency_weeks": signal_recency_weeks},
        "min_weeks": min_weeks,
        "detector_json": detector_json,
        "detector_age_days": detector_age_days,
        "schema_version": SCHEMA_VERSION,
    }


def generate_json_report(output: dict[str, Any], output_path: str) -> None:
    Path(output_path).write_text(json.dumps(output, indent=2, sort_keys=False), encoding="utf-8")


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def generate_markdown_report(output: dict[str, Any], output_path: str) -> None:
    run_context = output.get("run_context", {})
    checks = output.get("checks") or {}
    swing_levels = output.get("swing_levels") or {}

    lines = [
        "# Contrarian Confirmation Report (Shapiro Step 3)",
        "",
        f"Symbol: {output.get('symbol')}",
        f"Direction: `{output.get('direction')}`  (mode: {output.get('mode')})",
        f"As-of date: {run_context.get('as_of')}",
        f"Price source: `{run_context.get('price_symbol')}` "
        f"({run_context.get('price_source')}, proxy_used={run_context.get('proxy_used')})",
        "",
        "## Verdict",
        "",
        f"**{output.get('verdict')}** (confidence: {output.get('confidence')})",
        f"Reason: `{output.get('verdict_reason')}`",
        f"Weekly bars used: {output.get('weekly_bars_used')}",
        f"Last completed week: {output.get('last_completed_week')}",
        "",
        "## Checks",
        "",
        "| Check | Triggered | Week of | Detail |",
        "|---|---|---|---|",
    ]
    for name in ("weekly_key_reversal", "failed_extreme", "failed_breakout"):
        c = checks.get(name) or {}
        lines.append(
            f"| {name} | {c.get('triggered')} | {c.get('week_of') or 'n/a'} | {c.get('detail', '')} |"
        )
    cont = checks.get("continuation") or {}
    lines.append(
        f"| continuation (new closing extreme with crowd) | {cont.get('new_closing_extreme_with_crowd')} "
        f"| {cont.get('week_of') or 'n/a'} | veto check |"
    )

    lines += ["", "## Swing Levels", ""]
    if swing_levels:
        nsh = swing_levels.get("nearest_swing_high") or {}
        nsl = swing_levels.get("nearest_swing_low") or {}
        lines += [
            f"- Nearest swing high: {_fmt(nsh.get('price'))} (week of {nsh.get('week_of')}, "
            f"fallback={nsh.get('fallback')})",
            f"- Nearest swing low: {_fmt(nsl.get('price'))} (week of {nsl.get('week_of')}, "
            f"fallback={nsl.get('fallback')})",
            f"- Stop reference: {_fmt(swing_levels.get('stop_reference'))}",
        ]
    else:
        lines.append("Not computed (insufficient data).")

    if run_context.get("proxy_used"):
        lines += [
            "",
            "## Proxy Data Caveat",
            "",
            f"Price data for this analysis used an ETF proxy (`{run_context.get('price_symbol')}`) "
            "because the underlying futures symbol had no usable price feed on this key. ETF "
            "proxies carry tracking error, expense drag, and roll-timing differences versus the "
            "actual futures contract -- treat weekly level comparisons as approximate.",
        ]

    lines += [
        "",
        "## Methodology",
        "",
        "Verdict is synthesized from 3 weekly price-action detectors (weekly key "
        "reversal, failed extreme, failed breakout) evaluated against a "
        "continuation veto, per Jason Shapiro's contrarian process step 3. See "
        "`references/contrarian-confirmation-checklist.md` for the full "
        "methodology (definitions mirrored word-for-word between chart mode "
        "and this data-driven fallback). Verdict-only: never a trade "
        "recommendation on its own; sizing and entry decisions belong to "
        "downstream skills.",
        "",
    ]

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


# --- CLI -----------------------------------------------------------------


def _min_weeks_type(value: str) -> int:
    """argparse type for --min-weeks: must be a positive integer (>= 1).

    Without this, --min-weeks 0 (or negative) would silently defeat the
    `n < min_weeks` INSUFFICIENT_DATA floor check in
    weekly_price_action.run_weekly_price_action() -- `0 < 0` is False, so
    empty/near-empty price data would emit a (wrong) NOT_CONFIRMED instead
    of INSUFFICIENT_DATA (code review P3)."""
    try:
        ivalue = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--min-weeks must be an integer, got {value!r}") from exc
    if ivalue < 1:
        raise argparse.ArgumentTypeError(f"--min-weeks must be >= 1, got {ivalue}")
    return ivalue


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Confirm weekly price-action evidence of a reversal in a crowded "
        "market (Jason Shapiro contrarian process, step 3)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--symbol", required=True, help="COT symbol (mapped) or plain price ticker")
    parser.add_argument("--price-symbol", help="Override the price-source map (skips the chain)")
    parser.add_argument("--direction", choices=["CROWDED_LONG", "CROWDED_SHORT"])
    parser.add_argument("--detector-json", help="cot-contrarian-detector JSON report path")
    parser.add_argument("--max-detector-age-days", type=int, default=MAX_DETECTOR_AGE_DAYS_DEFAULT)
    parser.add_argument(
        "--as-of", default=date.today().strftime("%Y-%m-%d"), help="Information cutoff (YYYY-MM-DD)"
    )
    parser.add_argument("--swing-lookback-weeks", type=int, default=SWING_LOOKBACK_WEEKS_DEFAULT)
    parser.add_argument(
        "--extreme-lookback-weeks", type=int, default=EXTREME_LOOKBACK_WEEKS_DEFAULT
    )
    parser.add_argument("--signal-recency-weeks", type=int, default=SIGNAL_RECENCY_WEEKS_DEFAULT)
    parser.add_argument("--min-weeks", type=_min_weeks_type, default=MIN_WEEKS_DEFAULT)
    parser.add_argument("--output-dir", default="reports/")
    parser.add_argument("--format", choices=["json", "md", "both"], default="both")
    parser.add_argument(
        "--api-key", help="FMP API key (overrides FMP_API_KEY environment variable)"
    )
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    return parser.parse_args()


def _insufficient_data_output(
    symbol: str,
    direction: str | None,
    reason: str,
    run_context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "direction": direction,
        "mode": "data",
        "verdict": "INSUFFICIENT_DATA",
        "confidence": "MEDIUM",
        "verdict_reason": reason,
        "checks": None,
        "swing_levels": None,
        "weekly_bars_used": 0,
        "last_completed_week": None,
        "handoff": {
            "price_action": {
                "verdict": "INSUFFICIENT_DATA",
                "confidence": "MEDIUM",
                "stop_reference": None,
                "report_path": None,
            }
        },
        "run_context": run_context,
    }


def main() -> None:
    args = parse_arguments()
    print("=" * 72)
    print("Technical Analyst -- Contrarian Confirmation Mode (Shapiro Step 3)")
    print("=" * 72)

    symbol = args.symbol.upper()
    os.makedirs(args.output_dir, exist_ok=True)
    json_path = os.path.join(args.output_dir, f"ta_confirmation_{symbol}_{args.as_of}.json")
    md_path = os.path.join(args.output_dir, f"ta_confirmation_{symbol}_{args.as_of}.md")

    def base_run_context(
        price_symbol=None, price_source=None, proxy_used=False, detector_age_days=None
    ):
        return build_run_context(
            price_symbol,
            price_source,
            proxy_used,
            args.as_of,
            args.swing_lookback_weeks,
            args.extreme_lookback_weeks,
            args.signal_recency_weeks,
            args.min_weeks,
            args.detector_json,
            detector_age_days,
        )

    def emit(output: dict[str, Any]) -> None:
        # A report is always written (even for INSUFFICIENT_DATA -- exit 0,
        # never a crash), so report_path always points at it.
        output["handoff"]["price_action"]["report_path"] = json_path
        if args.format in ("json", "both"):
            generate_json_report(output, json_path)
        if args.format in ("md", "both"):
            generate_markdown_report(output, md_path)
        print(
            f"Verdict: {output['verdict']} (confidence: {output['confidence']}, reason: {output['verdict_reason']})"
        )
        if args.format in ("json", "both"):
            print(f"  JSON Report: {json_path}")
        if args.format in ("md", "both"):
            print(f"  Markdown Report: {md_path}")

    # --- Resolve direction ---------------------------------------------
    direction = args.direction
    detector_age_days = None
    if direction is None and args.detector_json:
        detector_data, error, load_reason = load_json_file(args.detector_json)
        if error:
            # Fail closed, exactly like every other degraded --detector-json
            # input below (malformed shape, missing data_date, stale, ...):
            # exit 0, report written, never a bare exit-1 with no report
            # (P1 regression, user re-review of PR #247).
            print(f"WARN: {error}", file=sys.stderr)
            insufficient_reason = (
                "detector_json_unreadable"
                if load_reason == "unreadable"
                else "detector_json_parse_error"
            )
            emit(_insufficient_data_output(symbol, None, insufficient_reason, base_run_context()))
            sys.exit(0)
        direction, reason, ctx = resolve_direction_from_detector(
            detector_data, symbol, args.as_of, args.max_detector_age_days
        )
        detector_age_days = ctx.get("detector_age_days")
        if direction is None:
            emit(
                _insufficient_data_output(
                    symbol, None, reason, base_run_context(detector_age_days=detector_age_days)
                )
            )
            sys.exit(0)

    if direction is None:
        emit(_insufficient_data_output(symbol, None, "no_direction_provided", base_run_context()))
        sys.exit(0)

    # --- Price data (fallback chain) ------------------------------------
    api_key = get_api_key(args.api_key)
    if not api_key:
        print("Error: FMP API key is required. Set FMP_API_KEY or use --api-key.", file=sys.stderr)
        sys.exit(1)

    if args.price_symbol:
        chain = [(args.price_symbol, "explicit_override", False)]
    else:
        chain = PRICE_SOURCE_CHAINS.get(symbol, [(symbol, "direct", False)])

    client = PriceClient(api_key=api_key, sleep_seconds=args.sleep_seconds)
    as_of_date = datetime.strptime(args.as_of, "%Y-%m-%d").date()
    weeks_needed = (
        max(args.extreme_lookback_weeks, args.min_weeks)
        + args.signal_recency_weeks
        + WEEKS_FETCH_BUFFER
    )
    from_date = (as_of_date - timedelta(weeks=weeks_needed)).strftime("%Y-%m-%d")
    to_date = args.as_of
    price_result = fetch_price_series(client, chain, from_date, to_date, as_of=args.as_of)

    run_context = base_run_context(
        price_result["price_symbol"],
        price_result.get("source_kind"),
        price_result["proxy_used"],
        detector_age_days,
    )

    if price_result["error"]:
        emit(_insufficient_data_output(symbol, direction, "no_price_source", run_context))
        sys.exit(0)

    # --- Run the pure detector pipeline ----------------------------------
    result = run_weekly_price_action(
        price_result["daily_bars"],
        direction,
        args.as_of,
        swing_lookback_weeks=args.swing_lookback_weeks,
        extreme_lookback_weeks=args.extreme_lookback_weeks,
        signal_recency_weeks=args.signal_recency_weeks,
        min_weeks=args.min_weeks,
    )

    stop_reference = result["swing_levels"]["stop_reference"] if result["swing_levels"] else None

    output = {
        "symbol": symbol,
        "direction": direction,
        "mode": "data",
        "verdict": result["verdict"],
        "confidence": result["confidence"],
        "verdict_reason": result["verdict_reason"],
        "checks": result["checks"],
        "swing_levels": result["swing_levels"],
        "weekly_bars_used": result["weekly_bars_used"],
        "last_completed_week": result["last_completed_week"],
        "handoff": {
            "price_action": {
                "verdict": result["verdict"],
                "confidence": result["confidence"],
                "stop_reference": stop_reference,
                "report_path": json_path,
            }
        },
        "run_context": run_context,
    }
    emit(output)


if __name__ == "__main__":
    main()
