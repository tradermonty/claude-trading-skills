#!/usr/bin/env python3
"""
KOSPI Breakout Screener — VCP Top 20 Candidate Scanner

Scans the KOSPI universe (FinanceDataReader) for Minervini VCP setups,
ranks candidates by composite score (Trend Template + VCP + Liquidity + RS),
and produces JSON + Markdown reports.

Examples:
    # Default: scan KOSPI stocks with Marcap >= 1조원, save Top 20
    python3 kospi_breakout_screener.py

    # Custom thresholds + larger universe + parallelism
    python3 kospi_breakout_screener.py \
        --min-marcap-bn 500 --top 30 --workers 12 --period 2y

    # KOSDAQ instead
    python3 kospi_breakout_screener.py --market KOSDAQ --min-marcap-bn 300

    # Use cache from prior run (skip OHLCV fetch)
    python3 kospi_breakout_screener.py --use-cache
"""

import argparse
import json
import math
import pickle
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean

CACHE_DIR = Path(__file__).parent / ".cache"
REPORTS_DIR = Path(__file__).parent / "reports"


def load_universe(market="KOSPI", min_marcap_bn=1000, max_tickers=None):
    """Fetch the ticker list and filter by market cap (in 억원, 100M KRW)."""
    import FinanceDataReader as fdr
    df = fdr.StockListing(market)
    df = df[df["Marcap"].notna() & (df["Marcap"] > 0)]
    df = df.sort_values("Marcap", ascending=False)
    cutoff = min_marcap_bn * 100_000_000  # 억원 → 원
    df = df[df["Marcap"] >= cutoff]
    if max_tickers:
        df = df.head(max_tickers)
    universe = []
    for _, row in df.iterrows():
        universe.append({
            "code": str(row["Code"]).zfill(6),
            "name": row["Name"],
            "marcap_bn_krw": int(row["Marcap"] / 100_000_000),
            "marcap_t_krw": round(row["Marcap"] / 1_000_000_000_000, 2),
        })
    return universe


def fetch_ohlcv(code, period_days=500, cache_date=None):
    """Fetch OHLCV via FDR, with optional disk cache keyed by date."""
    if cache_date:
        cf = CACHE_DIR / cache_date / f"{code}.pkl"
        if cf.exists():
            with open(cf, "rb") as f:
                return pickle.load(f)
    import FinanceDataReader as fdr
    end = datetime.now()
    start = end - timedelta(days=period_days * 1.5)  # extra to cover weekends
    df = fdr.DataReader(code, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    bars = []
    for idx, row in df.iterrows():
        try:
            o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
            v = int(row["Volume"])
        except (ValueError, TypeError, KeyError):
            continue
        if any(math.isnan(x) for x in (o, h, l, c)) or v < 0:
            continue
        if c <= 0 or h < l:
            continue
        bars.append({"date": idx.strftime("%Y-%m-%d"),
                     "open": o, "high": h, "low": l, "close": c, "volume": v})
    if cache_date:
        cf = CACHE_DIR / cache_date / f"{code}.pkl"
        cf.parent.mkdir(parents=True, exist_ok=True)
        with open(cf, "wb") as f:
            pickle.dump(bars, f)
    return bars


def find_swings(bars, window=5):
    swings = []
    for i in range(window, len(bars) - window):
        is_peak = all(bars[i]["high"] >= bars[i+k]["high"] for k in range(-window, window+1) if k != 0)
        is_trough = all(bars[i]["low"] <= bars[i+k]["low"] for k in range(-window, window+1) if k != 0)
        if is_peak:
            swings.append({"idx": i, "date": bars[i]["date"], "price": bars[i]["high"], "type": "PEAK"})
        elif is_trough:
            swings.append({"idx": i, "date": bars[i]["date"], "price": bars[i]["low"], "type": "TROUGH"})
    return swings


def detect_contractions(bars, swings, lookback_days):
    if not swings:
        return []
    cutoff = len(bars) - lookback_days
    recent = [s for s in swings if s["idx"] >= cutoff]
    contractions = []
    last_peak = None
    for s in recent:
        if s["type"] == "PEAK":
            if last_peak is None or s["price"] > last_peak["price"]:
                last_peak = s
        elif s["type"] == "TROUGH" and last_peak is not None and s["idx"] > last_peak["idx"]:
            depth_pct = (s["price"] - last_peak["price"]) / last_peak["price"] * 100
            contractions.append({
                "n": len(contractions) + 1,
                "high_date":  last_peak["date"], "high_price": last_peak["price"],
                "low_date":   s["date"],         "low_price":  s["price"],
                "depth_pct":  round(depth_pct, 2),
                "duration_days": s["idx"] - last_peak["idx"],
            })
            last_peak = None
    return contractions


def evaluate_vcp(contractions, bars):
    if len(contractions) < 2:
        return {"valid": False, "score": 0, "rating_band": "developing",
                "tightening": False, "volume_dryup": False,
                "last_contraction_depth_pct": None, "num_contractions": len(contractions)}
    depths = [abs(c["depth_pct"]) for c in contractions]
    tightening = all(depths[i] <= depths[i-1] for i in range(1, len(depths)))
    last_depth = depths[-1]

    last_c = contractions[-1]
    bars_in_last = [b for b in bars if last_c["high_date"] <= b["date"] <= last_c["low_date"]]
    vol_50d_avg = mean(b["volume"] for b in bars[-50:]) if len(bars) >= 50 else 1
    vol_in_last = mean(b["volume"] for b in bars_in_last) if bars_in_last else 0
    volume_dryup = vol_in_last < vol_50d_avg * 0.6 if vol_50d_avg else False

    score = 0
    if len(contractions) >= 3: score += 25
    elif len(contractions) >= 2: score += 15
    if tightening: score += 25
    if last_depth <= 7: score += 25
    elif last_depth <= 12: score += 15
    elif last_depth <= 18: score += 5
    if volume_dryup: score += 25

    if score >= 90:   rating_band = "textbook"
    elif score >= 80: rating_band = "strong"
    elif score >= 70: rating_band = "good"
    elif score >= 60: rating_band = "developing"
    else:             rating_band = "weak"

    valid = len(contractions) >= 2 and tightening and last_depth <= 15 and depths[0] <= 35
    return {"valid": valid, "score": score, "rating_band": rating_band,
            "tightening": tightening, "volume_dryup": volume_dryup,
            "last_contraction_depth_pct": -last_depth,
            "num_contractions": len(contractions)}


def trend_template(bars):
    if len(bars) < 200:
        return None
    closes = [b["close"] for b in bars]
    ma50  = mean(closes[-50:])
    ma150 = mean(closes[-150:])
    ma200 = mean(closes[-200:])
    ma200_30d = mean(closes[-230:-30]) if len(closes) >= 230 else ma200
    close = closes[-1]
    window_52w = bars[-252:] if len(bars) >= 252 else bars
    high_52w = max(b["high"] for b in window_52w)
    low_52w  = min(b["low"]  for b in window_52w)

    checks = [
        close > ma150 and close > ma200,
        ma150 > ma200,
        ma200 > ma200_30d,
        ma50 > ma150 and ma50 > ma200,
        close > ma50,
        close >= low_52w * 1.30,
        close >= high_52w * 0.75,
    ]
    return {"passed": sum(checks), "total": 7, "checks": checks,
            "ma50": ma50, "ma150": ma150, "ma200": ma200,
            "high_52w": high_52w, "low_52w": low_52w,
            "from_52w_high_pct": (close / high_52w - 1) * 100,
            "from_52w_low_pct":  (close / low_52w  - 1) * 100,
            "ma200_slope_30d_pct": (ma200 - ma200_30d) / ma200_30d * 100}


def compute_relative_strength(bars, period_days=126):
    """6-month price return as a simple RS proxy."""
    if len(bars) < period_days + 1:
        return None
    return (bars[-1]["close"] / bars[-period_days]["close"] - 1) * 100


def liquidity_score(bars):
    if len(bars) < 50:
        return 0
    avg_amount = mean(b["close"] * b["volume"] for b in bars[-50:])
    if avg_amount >= 100_000_000_000: return 25  # >= 1000억
    if avg_amount >=  50_000_000_000: return 20  # >= 500억
    if avg_amount >=  20_000_000_000: return 15  # >= 200억
    if avg_amount >=  10_000_000_000: return 10  # >= 100억
    if avg_amount >=   5_000_000_000: return 5
    return 0


def analyze(ticker_info, bars, lookback_days=120):
    code = ticker_info["code"]
    name = ticker_info["name"]
    if len(bars) < 200:
        return {"code": code, "name": name, "error": "insufficient_bars", "bars": len(bars)}

    tt = trend_template(bars)
    swings = find_swings(bars, 5)
    contractions = detect_contractions(bars, swings, lookback_days)
    vcp = evaluate_vcp(contractions, bars)
    rs_126 = compute_relative_strength(bars, 126)
    rs_63  = compute_relative_strength(bars, 63)
    liq = liquidity_score(bars)

    pivot = max((c["high_price"] for c in contractions), default=None)
    last_low = contractions[-1]["low_price"] if contractions else None
    risk_pct = None
    if pivot and last_low:
        worst_entry = pivot * 1.02
        stop = last_low * 0.99
        risk_pct = (worst_entry - stop) / worst_entry * 100

    # Composite ranking score (0-100)
    tt_score = tt["passed"] / 7 * 30
    vcp_score = vcp["score"] / 100 * 35
    liq_norm = liq / 25 * 15
    rs_score = 0
    if rs_126 is not None:
        rs_score = max(0, min(rs_126 / 2, 20))  # 40% return = max score

    composite = round(tt_score + vcp_score + liq_norm + rs_score, 1)

    # Hard filters for Minervini-style breakout consideration
    tt_pass = tt["passed"] >= 6
    risk_ok = risk_pct is not None and risk_pct <= 12
    vcp_ok  = vcp["score"] >= 50
    actionable = tt_pass and risk_ok and vcp_ok

    return {
        "code": code,
        "name": name,
        "marcap_bn_krw": ticker_info.get("marcap_bn_krw"),
        "marcap_t_krw":  ticker_info.get("marcap_t_krw"),
        "as_of": bars[-1]["date"],
        "close": bars[-1]["close"],
        "tt_passed": tt["passed"],
        "tt_from_high_pct":  round(tt["from_52w_high_pct"], 2),
        "tt_from_low_pct":   round(tt["from_52w_low_pct"], 2),
        "vcp_score": vcp["score"],
        "vcp_rating": vcp["rating_band"],
        "vcp_valid": vcp["valid"],
        "num_contractions": vcp["num_contractions"],
        "tightening": vcp["tightening"],
        "volume_dryup": vcp["volume_dryup"],
        "rs_126d_pct": round(rs_126, 2) if rs_126 is not None else None,
        "rs_63d_pct":  round(rs_63, 2)  if rs_63  is not None else None,
        "liquidity_score": liq,
        "composite_score": composite,
        "pivot": pivot,
        "last_contraction_low": last_low,
        "risk_pct": round(risk_pct, 2) if risk_pct is not None else None,
        "actionable": actionable,
    }


def scan_one(ticker_info, period_days, lookback_days, cache_date):
    try:
        bars = fetch_ohlcv(ticker_info["code"], period_days, cache_date)
        if len(bars) < 50:
            return {"code": ticker_info["code"], "name": ticker_info["name"], "error": "no_data"}
        return analyze(ticker_info, bars, lookback_days)
    except Exception as e:
        return {"code": ticker_info["code"], "name": ticker_info["name"], "error": str(e)[:80]}


def render_markdown(top, all_results, args, scan_meta):
    lines = []
    lines.append(f"# 📊 {args.market} Breakout Screener — VCP Top {args.top}\n")
    lines.append(f"**Scan Date:** {scan_meta['scan_date']}  ")
    lines.append(f"**Universe:** {scan_meta['universe_size']} 종목 ({args.market}, "
                 f"Marcap ≥ {args.min_marcap_bn:,}억원)  ")
    lines.append(f"**Analyzed:** {scan_meta['analyzed']} ({scan_meta['errors']} errors)  ")
    lines.append(f"**Duration:** {scan_meta['duration_sec']}초\n")

    actionable = [r for r in top if r.get("actionable")]
    lines.append(f"## 🎯 Actionable Breakout Candidates ({len(actionable)})\n")
    if not actionable:
        lines.append("_None today — market environment may not favor breakout setups._\n")
    else:
        lines.append("| # | Code | Name | Close | Mcap (조) | TT | VCP | Rating | Contr | RS 6M | Pivot | Stop | Risk% | Score |")
        lines.append("|---|------|------|------:|----------:|---:|----:|--------|------:|------:|------:|-----:|------:|------:|")
        for i, r in enumerate(actionable[:args.top], 1):
            lines.append(
                f"| {i} | {r['code']} | {r['name']} | {r['close']:,.0f} | "
                f"{r.get('marcap_t_krw','-')} | {r['tt_passed']}/7 | {r['vcp_score']} | "
                f"{r['vcp_rating']} | {r['num_contractions']} | "
                f"{r['rs_126d_pct']:+.1f}% | {r['pivot']:,.0f} | "
                f"{r['last_contraction_low']:,.0f} | {r['risk_pct']:.1f}% | "
                f"**{r['composite_score']}** |"
            )

    watchlist = [r for r in top if not r.get("actionable") and not r.get("error")
                 and r["tt_passed"] >= 5]
    lines.append(f"\n## 👁️ Watchlist — Developing Setups ({len(watchlist)})\n")
    if watchlist:
        lines.append("| # | Code | Name | TT | VCP | Rating | RS 6M | From-High | Risk% | Score |")
        lines.append("|---|------|------|---:|----:|--------|------:|----------:|------:|------:|")
        for i, r in enumerate(watchlist[:args.top], 1):
            risk = f"{r['risk_pct']:.1f}%" if r['risk_pct'] is not None else "-"
            lines.append(
                f"| {i} | {r['code']} | {r['name']} | {r['tt_passed']}/7 | "
                f"{r['vcp_score']} | {r['vcp_rating']} | {r['rs_126d_pct']:+.1f}% | "
                f"{r['tt_from_high_pct']:+.1f}% | {risk} | {r['composite_score']} |"
            )

    lines.append("\n## 📋 Filter Criteria\n")
    lines.append(f"- **Trend Template**: ≥ 6/7 passed")
    lines.append(f"- **VCP Score**: ≥ 50")
    lines.append(f"- **Risk (worst-entry → stop)**: ≤ 12%")
    lines.append(f"- **Composite Score**: `tt(30) + vcp(35) + liquidity(15) + rs(20)`\n")

    lines.append("## 🔄 Next Steps\n")
    lines.append("1. 상위 후보별로 **TradingView**에서 차트 확인 (`KRX:종목코드`)")
    lines.append("2. 정통 진입 검토 시: `vcp_detector.py --ticker <code>.KS` 단일 정밀 분석")
    lines.append("3. 진입 결정 시: `plans/<code>.json` 작성 + `daily_monitor.py` 등록")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="KOSPI Breakout Screener — VCP Top Candidates")
    p.add_argument("--market", default="KOSPI", choices=["KOSPI", "KOSDAQ", "KRX"])
    p.add_argument("--min-marcap-bn", type=int, default=1000, help="Min market cap (억원). Default 1000억=1조")
    p.add_argument("--max-tickers", type=int, default=None, help="Limit universe size (debug)")
    p.add_argument("--period-days", type=int, default=500)
    p.add_argument("--lookback-days", type=int, default=120)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--output-dir", default=str(REPORTS_DIR))
    p.add_argument("--use-cache", action="store_true", help="Reuse today's cache")
    p.add_argument("--no-cache", action="store_true", help="Skip cache write")
    args = p.parse_args()

    start_time = time.time()
    cache_date = datetime.now().strftime("%Y-%m-%d") if not args.no_cache else None
    if not args.use_cache and cache_date:
        # Invalidate by re-fetching; cache hits only if same day file exists
        pass

    print(f"📡 Loading {args.market} universe (Marcap ≥ {args.min_marcap_bn:,}억원)...",
          file=sys.stderr)
    universe = load_universe(args.market, args.min_marcap_bn, args.max_tickers)
    print(f"   Universe: {len(universe)} tickers", file=sys.stderr)
    if not universe:
        print("ERROR: empty universe", file=sys.stderr)
        sys.exit(1)

    print(f"🔍 Scanning with {args.workers} workers...", file=sys.stderr)
    results = []
    completed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(scan_one, t, args.period_days, args.lookback_days, cache_date): t
                   for t in universe}
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            completed += 1
            if completed % 25 == 0 or completed == len(universe):
                print(f"   [{completed}/{len(universe)}] processed", file=sys.stderr)

    errors  = [r for r in results if r.get("error")]
    success = [r for r in results if not r.get("error")]
    success.sort(key=lambda r: r.get("composite_score", 0), reverse=True)
    top = success[:max(args.top * 3, 60)]
    duration = round(time.time() - start_time, 1)

    scan_meta = {
        "scan_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": args.market,
        "universe_size": len(universe),
        "analyzed": len(success),
        "errors": len(errors),
        "duration_sec": duration,
    }

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    date_tag = datetime.now().strftime("%Y-%m-%d")
    json_path = out_dir / f"breakout_screener_{args.market}_{date_tag}.json"
    md_path   = out_dir / f"breakout_screener_{args.market}_{date_tag}.md"

    with open(json_path, "w") as f:
        json.dump({"meta": scan_meta, "top": success[:args.top * 3],
                   "all_results_count": len(results)}, f, indent=2, default=str)

    md = render_markdown(top, success, args, scan_meta)
    with open(md_path, "w") as f:
        f.write(md)

    actionable = [r for r in success if r.get("actionable")]
    print(f"\n{'='*72}")
    print(f"✅ Scan complete: {len(success)} analyzed, {len(actionable)} actionable")
    print(f"   Duration: {duration}s, Errors: {len(errors)}")
    print(f"📁 JSON: {json_path}")
    print(f"📁 MD:   {md_path}")
    if actionable:
        print(f"\n🎯 Top {min(5, len(actionable))} Actionable:")
        for r in actionable[:5]:
            print(f"   [{r['composite_score']:5.1f}] {r['code']} {r['name']:12s} "
                  f"TT={r['tt_passed']}/7 VCP={r['vcp_score']:3d} "
                  f"Pivot={r['pivot']:,.0f} Risk={r['risk_pct']:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
