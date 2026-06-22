#!/usr/bin/env python3
"""
VCP Contraction Auto-Detector
Detects Mark Minervini VCP patterns and Minervini Gate status from OHLCV data.

Examples:
    python3 vcp_detector.py --ticker 010060.KS --period 2y
    python3 vcp_detector.py --json /tmp/oci_holdings_daily.json
    python3 vcp_detector.py --csv data.csv --output report.json
"""

import argparse
import json
import sys
from pathlib import Path
from statistics import mean


def load_yfinance(ticker, period):
    import yfinance as yf
    df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=False)
    if df.empty:
        return []
    bars = []
    for idx, row in df.iterrows():
        bars.append({
            "date": idx.strftime("%Y-%m-%d"),
            "open": float(row["Open"].iloc[0] if hasattr(row["Open"], "iloc") else row["Open"]),
            "high": float(row["High"].iloc[0] if hasattr(row["High"], "iloc") else row["High"]),
            "low":  float(row["Low"].iloc[0]  if hasattr(row["Low"], "iloc")  else row["Low"]),
            "close":float(row["Close"].iloc[0]if hasattr(row["Close"], "iloc")else row["Close"]),
            "volume": int(row["Volume"].iloc[0] if hasattr(row["Volume"], "iloc") else row["Volume"]),
        })
    return bars


def load_csv(path):
    import csv
    bars = []
    with open(path) as f:
        for row in csv.DictReader(f):
            bars.append({
                "date": row.get("Date") or row.get("date"),
                "open": float(row.get("Open") or row.get("open")),
                "high": float(row.get("High") or row.get("high")),
                "low":  float(row.get("Low")  or row.get("low")),
                "close":float(row.get("Close")or row.get("close")),
                "volume": int(float(row.get("Volume") or row.get("volume") or 0)),
            })
    bars.sort(key=lambda b: b["date"])
    return bars


def load_json(path):
    with open(path) as f:
        bars = json.load(f)
    bars.sort(key=lambda b: b["date"])
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
                "high_date":  last_peak["date"],
                "high_price": last_peak["price"],
                "low_date":   s["date"],
                "low_price":  s["price"],
                "depth_pct":  round(depth_pct, 2),
                "duration_days": s["idx"] - last_peak["idx"],
            })
            last_peak = None
    return contractions


def evaluate_vcp(contractions, bars):
    if len(contractions) < 2:
        return {"valid": False, "score": 0, "rating_band": "developing",
                "reason": "Need >= 2 contractions"}

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

    valid = (
        len(contractions) >= 2 and
        tightening and
        last_depth <= 15 and
        depths[0] <= 35
    )

    return {
        "valid": valid,
        "score": score,
        "rating_band": rating_band,
        "tightening": tightening,
        "volume_dryup": volume_dryup,
        "last_contraction_depth_pct": -last_depth,
        "num_contractions": len(contractions),
    }


def trend_template(bars):
    if len(bars) < 200:
        return None
    closes = [b["close"] for b in bars]

    def ma(arr, n, i):
        return mean(arr[i+1-n:i+1])

    i = len(bars) - 1
    ma50  = ma(closes, 50,  i)
    ma150 = ma(closes, 150, i)
    ma200 = ma(closes, 200, i)
    ma200_30d = ma(closes, 200, i - 30) if i >= 229 else ma200

    window_52w = bars[-252:] if len(bars) >= 252 else bars
    high_52w = max(b["high"] for b in window_52w)
    low_52w  = min(b["low"]  for b in window_52w)
    close = closes[i]

    checks = {
        "1_close_above_150_200":    close > ma150 and close > ma200,
        "2_ma150_above_200":        ma150 > ma200,
        "3_ma200_rising_30d":       (ma200 - ma200_30d) / ma200_30d > 0,
        "4_ma50_above_150_200":     ma50 > ma150 and ma50 > ma200,
        "5_close_above_ma50":       close > ma50,
        "6_close_30pct_above_low":  close >= low_52w * 1.30,
        "7_close_within_25pct_high":close >= high_52w * 0.75,
    }
    return {
        "passed": sum(checks.values()),
        "total": 7,
        "checks": checks,
        "ma50":   round(ma50, 0),
        "ma150":  round(ma150, 0),
        "ma200":  round(ma200, 0),
        "high_52w": high_52w,
        "low_52w":  low_52w,
        "from_52w_high_pct": round((close / high_52w - 1) * 100, 2),
        "from_52w_low_pct":  round((close / low_52w  - 1) * 100, 2),
        "ma200_slope_30d_pct": round((ma200 - ma200_30d) / ma200_30d * 100, 2),
    }


def compute_atr(bars, period=14):
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        tr = max(
            bars[i]["high"] - bars[i]["low"],
            abs(bars[i]["high"] - bars[i-1]["close"]),
            abs(bars[i]["low"]  - bars[i-1]["close"]),
        )
        trs.append(tr)
    return mean(trs[-period:])


def main():
    p = argparse.ArgumentParser(description="VCP Contraction Auto-Detector")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--ticker", help="Yahoo Finance ticker (e.g. 010060.KS, AAPL)")
    src.add_argument("--csv",    help="CSV path with Date,Open,High,Low,Close,Volume")
    src.add_argument("--json",   help="JSON path (list of bar dicts)")
    p.add_argument("--period", default="2y")
    p.add_argument("--lookback-days", type=int, default=120)
    p.add_argument("--swing-window",  type=int, default=5)
    p.add_argument("--output", help="Save JSON report path")
    args = p.parse_args()

    if args.ticker:   bars = load_yfinance(args.ticker, args.period)
    elif args.csv:    bars = load_csv(args.csv)
    else:             bars = load_json(args.json)

    if len(bars) < 50:
        print(f"ERROR: insufficient bars ({len(bars)})", file=sys.stderr)
        sys.exit(1)

    swings = find_swings(bars, args.swing_window)
    contractions = detect_contractions(bars, swings, args.lookback_days)
    vcp = evaluate_vcp(contractions, bars)
    tt  = trend_template(bars)
    atr = compute_atr(bars, 14)

    pivot = max((c["high_price"] for c in contractions), default=None)
    last_low = contractions[-1]["low_price"] if contractions else None

    tt_pass = tt and tt["passed"] == 7
    vcp_pass = vcp["valid"] and vcp["rating_band"] in ("good", "strong", "textbook")
    verdict = "PASS" if (tt_pass and vcp_pass) else "REJECT"

    src_label = args.ticker or args.csv or args.json
    report = {
        "schema_version": "1.0",
        "as_of": bars[-1]["date"],
        "source": src_label,
        "current_price": bars[-1]["close"],
        "atr_14": round(atr, 0) if atr else None,
        "atr_pct": round(atr / bars[-1]["close"] * 100, 2) if atr else None,
        "bars_analyzed": len(bars),
        "trend_template": tt,
        "swings_recent": swings[-12:],
        "contractions": contractions,
        "vcp_assessment": vcp,
        "pivot_price": pivot,
        "last_contraction_low": last_low,
        "minervini_gate": {
            "trend_template_passed": tt_pass,
            "vcp_valid": vcp["valid"],
            "rating_band": vcp["rating_band"],
            "verdict": verdict,
        },
    }

    # Console report
    print(f"\n{'='*70}")
    print(f"📊 VCP Detector — {src_label}")
    print(f"{'='*70}")
    print(f"As of: {report['as_of']}  Close: {report['current_price']:,.0f}  Bars: {len(bars)}")
    print(f"ATR(14): {report['atr_14']:,.0f}  ({report['atr_pct']}%)" if atr else "")

    if tt:
        print(f"\n--- Trend Template: {tt['passed']}/7 ---")
        for k, v in tt["checks"].items():
            print(f"  {'✅' if v else '❌'} {k}")
        print(f"  MA50: {tt['ma50']:,.0f}  MA150: {tt['ma150']:,.0f}  MA200: {tt['ma200']:,.0f}")
        print(f"  52w: {tt['low_52w']:,.0f}~{tt['high_52w']:,.0f}  "
              f"from-high: {tt['from_52w_high_pct']:+.1f}%  from-low: {tt['from_52w_low_pct']:+.1f}%")

    print(f"\n--- Contractions ({len(contractions)}) ---")
    for c in contractions:
        print(f"  #{c['n']}: {c['high_date']} {c['high_price']:>9,.0f} → "
              f"{c['low_date']} {c['low_price']:>9,.0f}  "
              f"({c['depth_pct']:+.1f}%, {c['duration_days']}d)")

    print(f"\n--- VCP Assessment ---")
    print(f"  Valid:        {vcp['valid']}")
    print(f"  Score:        {vcp.get('score', 0)}/100")
    print(f"  Rating Band:  {vcp['rating_band']}")
    print(f"  Tightening:   {vcp.get('tightening')}")
    print(f"  Volume Dryup: {vcp.get('volume_dryup')}")

    print(f"\n--- Minervini Gate: {verdict} ---")
    if pivot:    print(f"  Pivot:              {pivot:,.0f}")
    if last_low: print(f"  Last Contraction:   {last_low:,.0f}")
    if pivot and last_low:
        worst_entry = pivot * 1.02
        stop = last_low * 0.99
        risk_pct = (worst_entry - stop) / worst_entry * 100
        print(f"  Worst Entry (+2%):  {worst_entry:,.0f}")
        print(f"  Stop (-1% buf):     {stop:,.0f}")
        print(f"  Risk %:             {risk_pct:.2f}%  {'✅ Pass' if risk_pct <= 8 else '❌ > 8%'}")

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n📁 Saved: {args.output}")

    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
