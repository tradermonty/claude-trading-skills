#!/usr/bin/env python3
"""Phase 1 entry point: parabolic short daily screener.

Pipeline:

1. Resolve the universe (S&P 500 by default; CSV override via
   ``--universe finviz-csv --universe-csv path/to/list.csv``).
2. Pull batch quotes + EOD history for each symbol.
3. Apply hard invalidation rules (mode-aware) before any scoring.
4. Score the survivors (5 factors → weighted composite → grade).
5. Evaluate state caps / warnings.
6. Emit JSON + Markdown into ``--output-dir`` (default ``reports/``).

A ``--dry-run`` mode reads a JSON fixture instead of FMP and produces the
same output, so the CLI can be smoke-tested without an API key.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Allow running as a script: scripts/ and scripts/calculators/ on sys.path.
SCRIPTS_DIR = Path(__file__).resolve().parent
CALCULATORS_DIR = SCRIPTS_DIR / "calculators"
for _p in (str(CALCULATORS_DIR), str(SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _market_calendar import count_sessions  # noqa: E402
from bar_normalizer import normalize_bars  # noqa: E402
from invalidation_rules import check_invalidation  # noqa: E402
from parabolic_report_generator import (  # noqa: E402
    build_json_report,
    build_markdown_report,
    render_candidate,
)
from parabolic_score_calculator import calculate_component_scores  # noqa: E402
from parabolic_scorer import calculate_composite_score, grade_at_or_above  # noqa: E402
from state_caps import evaluate_state_caps  # noqa: E402

logger = logging.getLogger("parabolic_short.screen")

DEFAULT_TOP = 25
DEFAULT_LOOKBACK_DAYS = 60
DEFAULT_MIN_ROC_5D = {"safe_largecap": 30.0, "classic_qm": 100.0}
ET = ZoneInfo("America/New_York")


# ---------- CLI ----------


def _iso_date_arg(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError("must be zero-padded YYYY-MM-DD")
    return value


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Parabolic Short — daily screener (Phase 1)")
    p.add_argument("--mode", choices=["safe_largecap", "classic_qm"], default="safe_largecap")
    p.add_argument("--universe", default="sp500")
    p.add_argument("--universe-csv", help="CSV path when --universe finviz-csv")
    p.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    p.add_argument("--min-roc-5d", type=float, default=None)
    p.add_argument("--min-ma20-extension-pct", type=float, default=25.0)
    p.add_argument("--min-atr-extension", type=float, default=4.0)
    p.add_argument("--min-price", type=float, default=5.00)
    p.add_argument("--min-adv-usd", type=float, default=None)
    p.add_argument("--min-market-cap", type=float, default=None)
    p.add_argument("--max-market-cap", type=float, default=None)
    p.add_argument(
        "--exclude-earnings-within-days",
        type=int,
        default=2,
        help="Calendar days; hard-invalidates a candidate when next earnings is within this window (forward-looking).",
    )
    p.add_argument(
        "--earnings-catalyst-window-days",
        type=int,
        default=10,
        help="Trading days; emits recent_earnings_catalyst warning when last earnings is within this window (backward-looking).",
    )
    p.add_argument("--top", type=int, default=DEFAULT_TOP)
    p.add_argument("--watch-min-grade", choices=["A", "B", "C", "D"], default="C")
    p.add_argument("--max-api-calls", type=int, default=800)
    p.add_argument("--api-key")
    p.add_argument("--output-dir", default="reports/")
    p.add_argument("--output-prefix", default="parabolic_short")
    p.add_argument("--as-of", type=_iso_date_arg, default=None, help="YYYY-MM-DD; default: today")
    p.add_argument("--dry-run", action="store_true", help="Read --fixture instead of FMP")
    p.add_argument("--fixture", help="JSON fixture path (used with --dry-run)")
    p.add_argument("--verbose", action="store_true")
    return p


# ---------- Earnings helpers ----------


def _count_trading_days(start: date, end: date) -> int:
    """Count XNYS sessions, exclusive of ``start``, inclusive of ``end``.

    Returns 0 when ``start == end`` and a negative number when
    ``end < start``.
    """
    if end < start:
        return -((start - end).days)
    return count_sessions(
        "XNYS",
        start,
        end,
        include_start=False,
        include_end=True,
    )


def _bars_on_or_before(bars_recent_first: list[dict], as_of_date: date) -> list[dict]:
    """Filter provider or fixture bars at the consumer boundary."""
    filtered: list[dict] = []
    for bar in bars_recent_first:
        try:
            bar_date = date.fromisoformat(str(bar.get("date", ""))[:10])
        except (TypeError, ValueError):
            continue
        if bar_date <= as_of_date:
            filtered.append(bar)
    return filtered


def _resolve_market_data_as_of(bars_recent_first: list[dict]) -> str | None:
    """Return YYYY-MM-DD of the latest bar, or None if unavailable.

    FMP historical responses are recent-first, so the first element holds
    the latest session. ``date`` is a string we truncate to YYYY-MM-DD to
    drop any time component.
    """
    if not bars_recent_first:
        return None
    raw = bars_recent_first[0].get("date")
    if not raw:
        return None
    return str(raw)[:10]


def _index_earnings_events(events: list[dict]) -> dict[str, list[dict]]:
    """Group an FMP earnings_calendar response by symbol.

    Defensive parser: skips rows missing ``symbol`` or ``date``,
    uppercases the symbol, and skips rows with unparsable ISO dates.
    FMP shapes vary by endpoint version (``symbol`` vs ``ticker``,
    ``date`` vs ``fiscalDateEnding``) — accept either.

    Returns ``{symbol: [{"date": "YYYY-MM-DD", "raw": original_event}, ...]}``
    sorted ascending by date.
    """
    by_symbol: dict[str, list[dict]] = {}
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        sym_raw = ev.get("symbol") or ev.get("ticker")
        date_raw = ev.get("date") or ev.get("fiscalDateEnding")
        if not sym_raw or not date_raw:
            continue
        try:
            ev_date = datetime.fromisoformat(str(date_raw)[:10]).date()
        except (TypeError, ValueError):
            continue
        sym = str(sym_raw).upper()
        by_symbol.setdefault(sym, []).append({"date": ev_date.isoformat(), "raw": ev})
    for sym in by_symbol:
        by_symbol[sym].sort(key=lambda e: e["date"])
    return by_symbol


def _compute_earnings_metadata(
    events_for_symbol: list[dict],
    market_data_as_of: date,
) -> dict:
    """Compute earnings metadata for one symbol relative to a reference date.

    ``trading_days_since_earnings`` is in **XNYS sessions**, used
    for the soft ``recent_earnings_catalyst`` warning.

    ``earnings_within_days`` is in **calendar days** to the next earnings
    event, used for the hard forward-looking blackout in
    ``invalidation_rules.check_invalidation``. Calendar days match the
    legacy semantic of ``earnings_blackout_days``.
    """
    last_date: date | None = None
    next_date: date | None = None
    for ev in events_for_symbol or []:
        try:
            ev_date = datetime.fromisoformat(ev["date"]).date()
        except (KeyError, TypeError, ValueError):
            continue
        if ev_date <= market_data_as_of:
            if last_date is None or ev_date > last_date:
                last_date = ev_date
        else:
            if next_date is None or ev_date < next_date:
                next_date = ev_date
    tdse: int | None = None
    if last_date is not None:
        tdse = _count_trading_days(last_date, market_data_as_of)
    cal_days_to_next: int | None = None
    if next_date is not None:
        cal_days_to_next = (next_date - market_data_as_of).days
    return {
        "last_earnings_date": last_date.isoformat() if last_date else None,
        "next_earnings_date": next_date.isoformat() if next_date else None,
        "trading_days_since_earnings": tdse,
        "earnings_within_days": cal_days_to_next,
    }


# ---------- Pipeline ----------


def screen_one_candidate(
    *,
    ticker: str,
    bars_recent_first: list[dict],
    quote: dict,
    profile: dict,
    earnings_meta: dict | None = None,
    market_data_as_of: str | None = None,
    mode: str,
    args: argparse.Namespace,
) -> dict | None:
    """Run the full pipeline on one symbol. Returns the rendered candidate
    dict (schema v1.0), or ``None`` if the symbol fails invalidation or
    scoring.

    ``earnings_meta`` carries the four earnings fields produced by
    :func:`_compute_earnings_metadata` (``last_earnings_date``,
    ``next_earnings_date``, ``trading_days_since_earnings``,
    ``earnings_within_days``). ``earnings_within_days`` (calendar days to
    the next earnings event) feeds the hard blackout in
    :func:`check_invalidation`; ``trading_days_since_earnings`` (trading
    days since the last earnings event) drives the soft
    ``recent_earnings_catalyst`` warning.

    ``market_data_as_of`` is YYYY-MM-DD of the latest bar; surfaced in the
    rendered candidate for downstream callers.
    """
    bars = normalize_bars(bars_recent_first, output_order="chronological")
    if len(bars) < 21:  # need at least 20 bars for MA / ATR / range expansion
        logger.debug("Rejected %s: insufficient_history (%d bars; need >=21)", ticker, len(bars))
        return None

    closes = [b["close"] for b in bars]
    opens = [b["open"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    volumes = [b["volume"] for b in bars]

    # Hard invalidation first — a single FMP profile fetch tells us most of
    # what we need; cheap to evaluate before any scoring math.
    market_cap = profile.get("mktCap") if profile else None
    days_listed = profile.get("days_listed_actual") if profile else None
    earnings_within_days = earnings_meta.get("earnings_within_days") if earnings_meta else None
    candidate_for_invalidation = {
        "ticker": ticker,
        "close": closes[-1],
        "market_cap_usd": market_cap,
        "adv_20d_usd": None,  # filled in below if liquidity passes
        "days_listed": days_listed,
        "earnings_within_days": earnings_within_days,
        "catalyst_blackout": False,
    }

    component_payload = calculate_component_scores(
        closes=closes, opens=opens, highs=highs, lows=lows, volumes=volumes
    )
    raw_metrics = component_payload["raw_metrics"]
    candidate_for_invalidation["adv_20d_usd"] = raw_metrics.get("adv_20d_usd")

    # Plumb the CLI override into the invalidation rules so a non-default
    # --exclude-earnings-within-days is actually honored by the hard
    # blackout (the mode-default would otherwise stay at 2 calendar days).
    invalidation = check_invalidation(
        candidate_for_invalidation,
        mode=mode,
        override={"earnings_blackout_days": args.exclude_earnings_within_days},
    )
    if invalidation["is_invalid"]:
        logger.debug("Rejected %s: invalidation (%s)", ticker, ", ".join(invalidation["reasons"]))
        return None

    # Threshold gates from CLI (these are softer than invalidation — they
    # filter watchlist size, not safety). Log per-ticker at DEBUG so
    # `--verbose` runs surface the smoke-runbook Tier-1 PASS evidence
    # ("--verbose documents at least one rejection reason").
    min_roc_5d = args.min_roc_5d if args.min_roc_5d is not None else DEFAULT_MIN_ROC_5D[mode]
    return_5d = raw_metrics.get("return_5d_pct") or 0
    if return_5d < min_roc_5d:
        logger.debug(
            "Rejected %s: min_roc_5d threshold not met (got %.2f%%, need >=%.2f%%)",
            ticker,
            return_5d,
            min_roc_5d,
        )
        return None
    ext_pct = raw_metrics.get("ext_20dma_pct") or 0
    if ext_pct < args.min_ma20_extension_pct:
        logger.debug(
            "Rejected %s: min_ma20_extension_pct threshold not met (got %.2f%%, need >=%.2f%%)",
            ticker,
            ext_pct,
            args.min_ma20_extension_pct,
        )
        return None
    ext_atr = raw_metrics.get("ext_20dma_atr")
    if ext_atr is None or ext_atr < args.min_atr_extension:
        logger.debug(
            "Rejected %s: min_atr_extension threshold not met (got %s, need >=%.2f)",
            ticker,
            f"{ext_atr:.2f}" if ext_atr is not None else "None",
            args.min_atr_extension,
        )
        return None

    composite = calculate_composite_score(component_payload["components"])

    state = evaluate_state_caps(
        {
            "close": closes[-1],
            "session_high": highs[-1],
            "session_low": lows[-1],
            "is_at_52w_high_recently": (closes[-1] >= max(highs[-min(252, len(highs)) :]) * 0.999),
            "volume_ratio_20d": raw_metrics.get("volume_ratio_20d"),
            "premarket_gap_pct": None,
        }
    )

    # Soft warning: last earnings within the catalyst window. Routes through
    # the existing warnings list so Phase 2 (manual_reasons.py) treats it as
    # an advisory manual reason — Phase 2 still allows trading without
    # forcing trade_allowed_without_manual=False.
    tdse = earnings_meta.get("trading_days_since_earnings") if earnings_meta else None
    if tdse is not None and tdse <= args.earnings_catalyst_window_days:
        if "recent_earnings_catalyst" not in state["warnings"]:
            state["warnings"].append("recent_earnings_catalyst")

    key_levels = {
        "dma_10": raw_metrics.get("dma_10"),
        "dma_20": raw_metrics.get("dma_20"),
        "dma_50": raw_metrics.get("dma_50"),
        "prior_close": closes[-1],
        "prior_close_source": "fmp_historical_eod",
        "session_high": highs[-1],
        "session_low": lows[-1],
    }

    return render_candidate(
        ticker=ticker,
        composite_result=composite,
        component_scores_raw=component_payload["components"],
        raw_metrics=raw_metrics,
        state_caps=state["state_caps"],
        warnings=state["warnings"],
        key_levels=key_levels,
        invalidation_checks_passed=True,
        earnings_meta=earnings_meta,
        earnings_blackout_days=args.exclude_earnings_within_days,
        market_data_as_of=market_data_as_of,
        market_cap_usd=market_cap,
    )


def run_dry_run(
    fixture_path: str,
    args: argparse.Namespace,
    run_date: str | None = None,
) -> list[dict]:
    """Run the pipeline against an in-memory fixture JSON.

    Fixture shape (all earnings/market_data fields are optional)::

        {"symbols": [{"ticker": "...", "bars": [...recent-first OHLCV...],
                      "quote": {...}, "profile": {...},
                      "earnings_within_days": int|null,
                      "last_earnings_date": "YYYY-MM-DD"|null,
                      "next_earnings_date": "YYYY-MM-DD"|null,
                      "trading_days_since_earnings": int|null,
                      "market_data_as_of": "YYYY-MM-DD"|null}, ...]}

    Precedence for ``trading_days_since_earnings``:

    1. If the fixture provides an explicit value, use it as-is.
    2. Otherwise, compute it from ``last_earnings_date`` and
       ``market_data_as_of`` (or the latest bar date) when both are known.
    3. Otherwise, leave as ``None``.

    ``market_data_as_of`` defaults to the latest bar's date when not
    supplied by the fixture.
    """
    with open(fixture_path, encoding="utf-8") as fh:
        fixture = json.load(fh)
    out: list[dict] = []
    ceiling = date.fromisoformat(run_date) if run_date is not None else None
    for sym in fixture["symbols"]:
        bars = sym["bars"]
        if ceiling is not None:
            bars = _bars_on_or_before(bars, ceiling)
            if not bars:
                continue
        market_data_as_of = sym.get("market_data_as_of") or _resolve_market_data_as_of(bars)
        if ceiling is not None and market_data_as_of:
            explicit_date = date.fromisoformat(market_data_as_of)
            if explicit_date > ceiling:
                raise ValueError(
                    f"fixture market_data_as_of {market_data_as_of} exceeds --as-of {run_date}"
                )
        # Build earnings_meta from explicit fixture fields, falling back to
        # computed values where possible.
        last_iso = sym.get("last_earnings_date")
        next_iso = sym.get("next_earnings_date")
        explicit_tdse = sym.get("trading_days_since_earnings")
        explicit_within = sym.get("earnings_within_days")
        tdse = explicit_tdse
        if tdse is None and last_iso and market_data_as_of:
            try:
                tdse = _count_trading_days(
                    datetime.fromisoformat(last_iso).date(),
                    datetime.fromisoformat(market_data_as_of).date(),
                )
            except ValueError:
                tdse = None
        within = explicit_within
        if within is None and next_iso and market_data_as_of:
            try:
                within = (
                    datetime.fromisoformat(next_iso).date()
                    - datetime.fromisoformat(market_data_as_of).date()
                ).days
            except ValueError:
                within = None
        earnings_meta = {
            "last_earnings_date": last_iso,
            "next_earnings_date": next_iso,
            "trading_days_since_earnings": tdse,
            "earnings_within_days": within,
        }
        c = screen_one_candidate(
            ticker=sym["ticker"],
            bars_recent_first=bars,
            quote=sym.get("quote", {}),
            profile=sym.get("profile", {}),
            earnings_meta=earnings_meta,
            market_data_as_of=market_data_as_of,
            mode=args.mode,
            args=args,
        )
        if c is not None:
            out.append(c)
    return out


def run_live(args: argparse.Namespace, run_date: str) -> list[dict]:
    """Pull universe + per-symbol data from FMP and run the pipeline.

    ``run_date`` (YYYY-MM-DD, normally ``args.as_of`` or today) centers
    the bulk earnings-calendar fetch window. Per-symbol
    ``market_data_as_of`` is then derived from each symbol's latest bar.
    """
    from fmp_client import FMPClient  # local import: only needed in live mode

    api_key = args.api_key or os.getenv("FMP_API_KEY")
    if not api_key:
        raise SystemExit("FMP_API_KEY is required (env or --api-key) unless --dry-run is used")
    client = FMPClient(api_key=api_key)

    symbols = _resolve_universe(args, client)
    logger.info("Universe size: %d", len(symbols))

    # One bulk earnings-calendar fetch covers the catalyst window backward
    # and the blackout window forward. The +7 calendar-day buffer absorbs
    # weekends/holidays at the window edges so per-symbol
    # market_data_as_of values that drift slightly from run_date still
    # land inside the fetched range.
    catalyst_window = args.earnings_catalyst_window_days
    exclude_window = args.exclude_earnings_within_days
    center = date.fromisoformat(run_date)
    from_date = (center - timedelta(days=catalyst_window + 7)).isoformat()
    to_date = (center + timedelta(days=exclude_window + 7)).isoformat()
    raw_events = client.get_earnings_calendar(from_date, to_date) or []
    earnings_by_symbol = _index_earnings_events(raw_events)

    out: list[dict] = []
    for sym in symbols:
        if client.api_calls_made >= args.max_api_calls:
            logger.warning("Hit max-api-calls budget at %d", client.api_calls_made)
            break
        bars_payload = client.get_historical_prices(sym, days=args.lookback_days)
        if not bars_payload or "historical" not in bars_payload:
            continue
        profile = client.get_company_profile(sym) or {}
        bars_recent_first = _bars_on_or_before(bars_payload["historical"], center)
        if not bars_recent_first:
            logger.warning("No %s bars on or before --as-of %s", sym, run_date)
            continue
        market_data_as_of = _resolve_market_data_as_of(bars_recent_first)
        earnings_meta: dict | None = None
        if market_data_as_of:
            try:
                ref_date = datetime.fromisoformat(market_data_as_of).date()
            except ValueError:
                ref_date = None
            if ref_date is not None:
                earnings_meta = _compute_earnings_metadata(
                    earnings_by_symbol.get(sym.upper(), []),
                    ref_date,
                )
        c = screen_one_candidate(
            ticker=sym,
            bars_recent_first=bars_recent_first,
            quote={},
            profile=profile,
            earnings_meta=earnings_meta,
            market_data_as_of=market_data_as_of,
            mode=args.mode,
            args=args,
        )
        if c is not None:
            out.append(c)
    return out


def _resolve_universe(args: argparse.Namespace, client) -> list[str]:
    if args.universe == "sp500":
        rows = client.get_sp500_constituents() or []
        return [r["symbol"] for r in rows if r.get("symbol")]
    if args.universe == "finviz-csv":
        if not args.universe_csv:
            raise SystemExit("--universe finviz-csv requires --universe-csv")
        with open(args.universe_csv, encoding="utf-8") as fh:
            return [line.strip().split(",")[0] for line in fh if line.strip()]
    raise SystemExit(f"--universe {args.universe!r} not implemented in MVP")


# ---------- Output ----------


def write_outputs(report: dict, output_dir: str, prefix: str, as_of: str) -> tuple[Path, Path]:
    odir = Path(output_dir)
    odir.mkdir(parents=True, exist_ok=True)
    json_path = odir / f"{prefix}_{as_of}.json"
    md_path = odir / f"{prefix}_{as_of}.md"
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    md_path.write_text(build_markdown_report(report), encoding="utf-8")
    return json_path, md_path


# ---------- Main ----------


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    # Quiet HTTP-library noise so per-ticker rejection logs are
    # visible under --verbose. Without this, urllib3.connectionpool
    # DEBUG lines bury the application-level rejection messages the
    # smoke runbook's Tier 1 PASS criterion looks for.
    for noisy in ("urllib3", "urllib3.connectionpool"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    live_date = datetime.now(ET).date()
    as_of = args.as_of or live_date.isoformat()

    if not args.dry_run and args.as_of is not None and date.fromisoformat(as_of) != live_date:
        print(
            "ERROR: historical --as-of is supported only with --dry-run fixture data; "
            "the live universe and profile endpoints are not point-in-time",
            file=sys.stderr,
        )
        return 2

    if args.dry_run:
        if not args.fixture:
            raise SystemExit("--dry-run requires --fixture <path>")
        try:
            candidates = run_dry_run(args.fixture, args, run_date=as_of)
        except (TypeError, ValueError) as exc:
            raise SystemExit(f"Invalid dry-run data: {exc}") from exc
        data_source = "fixture"
    else:
        candidates = run_live(args, run_date=as_of)
        data_source = "FMP"

    # Apply --watch-min-grade and --top after scoring/grading.
    candidates = [c for c in candidates if grade_at_or_above(c["rank"], args.watch_min_grade)]
    candidates.sort(key=lambda c: -c["score"])
    candidates = candidates[: args.top]

    report = build_json_report(
        candidates=candidates,
        mode=args.mode,
        universe=args.universe,
        as_of=as_of,
        run_date=as_of,
        data_source=data_source,
    )
    json_path, md_path = write_outputs(report, args.output_dir, args.output_prefix, as_of)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
