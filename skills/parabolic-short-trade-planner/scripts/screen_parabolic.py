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
from datetime import datetime
from pathlib import Path

# Allow running as a script: scripts/ and scripts/calculators/ on sys.path.
SCRIPTS_DIR = Path(__file__).resolve().parent
CALCULATORS_DIR = SCRIPTS_DIR / "calculators"
for _p in (str(CALCULATORS_DIR), str(SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

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


# ---------- CLI ----------


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
    p.add_argument("--exclude-earnings-within-days", type=int, default=2)
    p.add_argument("--top", type=int, default=DEFAULT_TOP)
    p.add_argument("--watch-min-grade", choices=["A", "B", "C", "D"], default="C")
    p.add_argument("--max-api-calls", type=int, default=800)
    p.add_argument("--api-key")
    p.add_argument("--output-dir", default="reports/")
    p.add_argument("--output-prefix", default="parabolic_short")
    p.add_argument("--as-of", default=None, help="YYYY-MM-DD; default: today")
    p.add_argument("--dry-run", action="store_true", help="Read --fixture instead of FMP")
    p.add_argument("--fixture", help="JSON fixture path (used with --dry-run)")
    p.add_argument("--verbose", action="store_true")
    return p


# ---------- Pipeline ----------


def screen_one_candidate(
    *,
    ticker: str,
    bars_recent_first: list[dict],
    quote: dict,
    profile: dict,
    earnings_within_days: int | None,
    mode: str,
    args: argparse.Namespace,
) -> dict | None:
    """Run the full pipeline on one symbol. Returns the rendered candidate
    dict (schema v1.0), or ``None`` if the symbol fails invalidation or
    scoring.
    """
    bars = normalize_bars(bars_recent_first, output_order="chronological")
    if len(bars) < 21:  # need at least 20 bars for MA / ATR / range expansion
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

    invalidation = check_invalidation(candidate_for_invalidation, mode=mode)
    if invalidation["is_invalid"]:
        logger.debug("%s rejected: %s", ticker, ", ".join(invalidation["reasons"]))
        return None

    # Threshold gates from CLI (these are softer than invalidation — they
    # filter watchlist size, not safety).
    min_roc_5d = args.min_roc_5d if args.min_roc_5d is not None else DEFAULT_MIN_ROC_5D[mode]
    if (raw_metrics.get("return_5d_pct") or 0) < min_roc_5d:
        return None
    if (raw_metrics.get("ext_20dma_pct") or 0) < args.min_ma20_extension_pct:
        return None
    ext_atr = raw_metrics.get("ext_20dma_atr")
    if ext_atr is None or ext_atr < args.min_atr_extension:
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
        earnings_within_days=earnings_within_days,
        market_cap_usd=market_cap,
    )


def run_dry_run(fixture_path: str, args: argparse.Namespace) -> list[dict]:
    """Run the pipeline against an in-memory fixture JSON.

    Fixture shape::

        {"symbols": [{"ticker": "...", "bars": [...recent-first OHLCV...],
                      "quote": {...}, "profile": {...},
                      "earnings_within_days": int|null}, ...]}
    """
    with open(fixture_path, encoding="utf-8") as fh:
        fixture = json.load(fh)
    out: list[dict] = []
    for sym in fixture["symbols"]:
        c = screen_one_candidate(
            ticker=sym["ticker"],
            bars_recent_first=sym["bars"],
            quote=sym.get("quote", {}),
            profile=sym.get("profile", {}),
            earnings_within_days=sym.get("earnings_within_days"),
            mode=args.mode,
            args=args,
        )
        if c is not None:
            out.append(c)
    return out


def run_live(args: argparse.Namespace) -> list[dict]:
    """Pull universe + per-symbol data from FMP and run the pipeline."""
    from fmp_client import FMPClient  # local import: only needed in live mode

    api_key = args.api_key or os.getenv("FMP_API_KEY")
    if not api_key:
        raise SystemExit("FMP_API_KEY is required (env or --api-key) unless --dry-run is used")
    client = FMPClient(api_key=api_key)

    symbols = _resolve_universe(args, client)
    logger.info("Universe size: %d", len(symbols))

    out: list[dict] = []
    for sym in symbols:
        if client.api_calls_made >= args.max_api_calls:
            logger.warning("Hit max-api-calls budget at %d", client.api_calls_made)
            break
        bars_payload = client.get_historical_prices(sym, days=args.lookback_days)
        if not bars_payload or "historical" not in bars_payload:
            continue
        profile = client.get_company_profile(sym) or {}
        c = screen_one_candidate(
            ticker=sym,
            bars_recent_first=bars_payload["historical"],
            quote={},
            profile=profile,
            earnings_within_days=None,  # earnings calendar lookup is per-symbol; skip in MVP
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
    as_of = args.as_of or datetime.now().date().isoformat()

    if args.dry_run:
        if not args.fixture:
            raise SystemExit("--dry-run requires --fixture <path>")
        candidates = run_dry_run(args.fixture, args)
        data_source = "fixture"
    else:
        candidates = run_live(args)
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
        data_source=data_source,
    )
    json_path, md_path = write_outputs(report, args.output_dir, args.output_prefix, as_of)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
