#!/usr/bin/env python3
"""
Daily Trade Setup Monitor & Alarm
Checks watchlist tickers against trigger conditions, posts alerts.

Examples:
    python3 daily_monitor.py --config oci_plan.json
    python3 daily_monitor.py --ticker 010060.KS --entry 260000 --entry 220000 \
        --stop 195000 --target 320000 --target 395000 --target 440000
    python3 daily_monitor.py --ticker AAPL --entry 180 --stop 170 --target 200

Exit codes:
    0 = OK
    1 = WARN-level alerts fired
    2 = CRITICAL alerts fired (stop hit / setup broken)
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean


def load_yfinance(ticker, period):
    import yfinance as yf
    import math
    df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=False)
    if df.empty:
        return []
    bars = []
    for idx, row in df.iterrows():
        def f(col):
            v = row[col]
            v = v.iloc[0] if hasattr(v, "iloc") else v
            return float(v)
        try:
            o, h, l, c = f("Open"), f("High"), f("Low"), f("Close")
            v = int(f("Volume"))
        except (ValueError, TypeError):
            continue
        if any(math.isnan(x) for x in (o, h, l, c)):
            continue
        bars.append({
            "date": idx.strftime("%Y-%m-%d"),
            "open": o, "high": h, "low": l, "close": c, "volume": v,
        })
    return bars


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

    checks = {
        "close>MA150,200":   close > ma150 and close > ma200,
        "MA150>MA200":       ma150 > ma200,
        "MA200 rising":      ma200 > ma200_30d,
        "MA50>MA150,200":    ma50 > ma150 and ma50 > ma200,
        "close>MA50":        close > ma50,
        "52wLow+30%":        close >= low_52w * 1.30,
        "52wHigh-25%":       close >= high_52w * 0.75,
    }
    return {
        "passed": sum(checks.values()), "total": 7, "checks": checks,
        "ma50": ma50, "ma150": ma150, "ma200": ma200,
        "high_52w": high_52w, "low_52w": low_52w,
    }


def count_distribution_days(bars, lookback=25, threshold=-0.2):
    count, days = 0, []
    start = max(1, len(bars) - lookback)
    for i in range(start, len(bars)):
        chg = (bars[i]["close"] - bars[i-1]["close"]) / bars[i-1]["close"] * 100
        if chg < threshold and bars[i]["volume"] > bars[i-1]["volume"]:
            count += 1
            days.append({"date": bars[i]["date"], "chg_pct": round(chg, 2)})
    return count, days


def evaluate_triggers(bars, plan):
    if len(bars) < 2:
        return []
    current = bars[-1]
    prev = bars[-2]
    alerts = []

    for entry in plan.get("entries", []):
        if current["low"] <= entry["price"] <= current["high"]:
            alerts.append({
                "type": "ENTRY_HIT", "level": entry["price"],
                "label": entry.get("label", ""), "severity": "INFO",
                "msg": f"📍 진입가 ₩{entry['price']:,.0f} 도달 ({entry.get('label','')})",
            })

    stop = plan.get("stop_loss")
    if stop:
        if current["close"] <= stop:
            alerts.append({
                "type": "STOP_HIT_CLOSE", "level": stop, "severity": "CRITICAL",
                "msg": f"🆘 손절선 ₩{stop:,.0f} 종가 이탈 — 즉시 청산",
            })
        elif current["low"] <= stop:
            alerts.append({
                "type": "STOP_TOUCHED", "level": stop, "severity": "WARN",
                "msg": f"⚠️ 손절선 ₩{stop:,.0f} 일중 터치 (종가는 회복)",
            })

    for tgt in plan.get("targets", []):
        if current["high"] >= tgt["price"] > prev["high"]:
            alerts.append({
                "type": "TARGET_HIT", "level": tgt["price"],
                "label": tgt.get("label", ""), "severity": "INFO",
                "msg": f"🎯 목표가 ₩{tgt['price']:,.0f} 도달 ({tgt.get('label','')})",
            })

    chg_pct = (current["close"] - prev["close"]) / prev["close"] * 100
    if chg_pct <= -5:
        alerts.append({
            "type": "BIG_DOWN", "level": None, "severity": "WARN",
            "msg": f"🔴 큰 하락 {chg_pct:+.2f}%",
        })

    vol_50d = mean(b["volume"] for b in bars[-51:-1]) if len(bars) >= 51 else current["volume"]
    rvol = current["volume"] / vol_50d if vol_50d else 0
    if rvol >= 2.0 and chg_pct < -0.5:
        alerts.append({
            "type": "DISTRIBUTION_DAY", "level": None, "severity": "WARN",
            "msg": f"⚠️ 분배일 가능성 (RVOL {rvol:.1f}x, {chg_pct:+.2f}%)",
        })

    pivot = plan.get("pivot")
    if pivot and current["close"] > pivot and prev["close"] <= pivot:
        if rvol >= 1.5:
            alerts.append({
                "type": "BREAKOUT_CONFIRMED", "level": pivot, "severity": "INFO",
                "msg": f"🚀 피봇 ₩{pivot:,.0f} 돌파 + RVOL {rvol:.1f}x — 진입 검토",
            })
        else:
            alerts.append({
                "type": "BREAKOUT_LOW_VOL", "level": pivot, "severity": "WARN",
                "msg": f"🟡 피봇 돌파했지만 RVOL {rvol:.1f}x (1.5 미달)",
            })

    return alerts


def build_plan(args):
    if args.config:
        with open(args.config) as f:
            plan = json.load(f)
        plan.setdefault("ticker", args.ticker)
        return plan
    return {
        "ticker": args.ticker,
        "entries": [{"price": p, "label": f"Entry{i+1}"} for i, p in enumerate(args.entry or [])],
        "stop_loss": args.stop,
        "targets": [{"price": p, "label": f"T{i+1}"} for i, p in enumerate(args.target or [])],
        "pivot": args.pivot,
    }


def main():
    p = argparse.ArgumentParser(description="Daily Trade Setup Monitor")
    p.add_argument("--ticker", required=True, help="Yahoo Finance ticker")
    p.add_argument("--config", help="Plan JSON config (overrides CLI flags)")
    p.add_argument("--entry",  type=float, action="append", help="Entry price (repeatable)")
    p.add_argument("--stop",   type=float, help="Stop-loss price")
    p.add_argument("--target", type=float, action="append", help="Target price (repeatable)")
    p.add_argument("--pivot",  type=float, help="Pivot breakout level")
    p.add_argument("--period", default="1y")
    p.add_argument("--output-dir", default="./monitor_reports")
    p.add_argument("--quiet", action="store_true", help="Only print alerts")
    args = p.parse_args()

    plan = build_plan(args)

    print(f"📡 {args.ticker} fetching...", file=sys.stderr)
    bars = load_yfinance(args.ticker, args.period)
    if len(bars) < 50:
        print(f"ERROR: insufficient bars ({len(bars)})", file=sys.stderr)
        sys.exit(3)

    current = bars[-1]
    prev = bars[-2]
    chg_pct = (current["close"] - prev["close"]) / prev["close"] * 100
    tt = trend_template(bars)
    d_count, d_days = count_distribution_days(bars, 25)
    alerts = evaluate_triggers(bars, plan)

    if not args.quiet:
        print(f"\n{'='*72}")
        print(f"📊 Daily Monitor — {args.ticker}  {current['date']}")
        print(f"{'='*72}")
        print(f"Close:  {current['close']:>10,.0f}  ({chg_pct:+.2f}%)")
        print(f"High:   {current['high']:>10,.0f}")
        print(f"Low:    {current['low']:>10,.0f}")
        print(f"Volume: {current['volume']:>10,}")

        if tt:
            print(f"\n--- Trend Template: {tt['passed']}/7 ---")
            for k, v in tt["checks"].items():
                print(f"  {'✅' if v else '❌'} {k}")
            print(f"  MA50: {tt['ma50']:,.0f}  MA200: {tt['ma200']:,.0f}  52wH: {tt['high_52w']:,.0f}")
        else:
            print(f"\n--- Trend Template: insufficient bars (< 200), use --period 2y+ ---")

        print(f"\n--- Distribution Days (25d): {d_count} ---")
        for d in d_days[-5:]:
            print(f"  {d['date']}: {d['chg_pct']:+.2f}%")
        if d_count >= 5:
            print(f"  ⚠️ {d_count} D-Days → 시장/종목 압박")

        print(f"\n--- Plan ---")
        for e in plan.get("entries", []):
            print(f"  📍 Entry:  {e['price']:>10,.0f} ({e.get('label','')})")
        if plan.get("stop_loss"):
            print(f"  🛡️ Stop:   {plan['stop_loss']:>10,.0f}")
        if plan.get("pivot"):
            print(f"  🚀 Pivot:  {plan['pivot']:>10,.0f}")
        for t in plan.get("targets", []):
            print(f"  🎯 Target: {t['price']:>10,.0f} ({t.get('label','')})")

    print(f"\n--- 🚨 ALERTS ({len(alerts)}) ---")
    if not alerts:
        print("  (no triggers fired today)")
    for a in alerts:
        icon = {"CRITICAL": "🔴", "WARN": "🟡", "INFO": "🟢"}.get(a["severity"], "  ")
        print(f"  {icon} [{a['severity']}] {a['msg']}")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"monitor_{args.ticker.replace('.','_')}_{current['date']}.json"
    with open(out_file, "w") as f:
        json.dump({
            "ticker": args.ticker,
            "as_of": current["date"],
            "current": current,
            "change_pct": round(chg_pct, 2),
            "trend_template": tt,
            "distribution_days": {"count": d_count, "recent": d_days[-10:]},
            "plan": plan,
            "alerts": alerts,
        }, f, indent=2, default=str)
    print(f"\n📁 {out_file}", file=sys.stderr)

    if any(a["severity"] == "CRITICAL" for a in alerts): sys.exit(2)
    if any(a["severity"] == "WARN" for a in alerts):     sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
