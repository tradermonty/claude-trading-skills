"""Generate the fictional FMP-shaped fixture for the earnings-weekly replay.

Deterministic: fixed seeds, no clock, no network. All symbols and companies are
fictional. Output: JSON written to the path given as argv[1].

Reproduce the committed fixture byte for byte:
    python3 scripts/dev/generate_earnings_weekly_fixture.py \
        examples/workflows/earnings-weekly/replay-inputs/fmp-fixture.json
scripts/tests/test_workflow_replay_earnings_weekly.py verifies this.
"""

import json
import random
import sys
from datetime import date, timedelta

END = date(2026, 11, 6)
N_DAYS = 250


def trading_days():
    days = []
    d = END
    while len(days) < N_DAYS:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    return days


DAYS = trading_days()


def interp(knots, d):
    """Linear interpolation of close over (date, price) knots."""
    knots = sorted(knots)
    if d <= knots[0][0]:
        return knots[0][1]
    for (d0, p0), (d1, p1) in zip(knots, knots[1:]):
        if d0 <= d <= d1:
            span = (d1 - d0).days or 1
            return p0 + (p1 - p0) * ((d - d0).days / span)
    return knots[-1][1]


def build(symbol, seed, knots, explicit, base_volume=1_500_000):
    rng = random.Random(seed)
    rows = []
    for d in DAYS:
        iso = d.isoformat()
        if iso in explicit:
            o, h, lo, c, v = explicit[iso]
        else:
            c = interp(knots, d) * (1 + rng.uniform(-0.004, 0.004))
            o = c * (1 + rng.uniform(-0.003, 0.003))
            h = max(o, c) * (1 + rng.uniform(0.001, 0.006))
            lo = min(o, c) * (1 - rng.uniform(0.001, 0.006))
            v = int(base_volume * rng.uniform(0.85, 1.15))
        rows.append(
            {
                "date": iso,
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(lo, 2),
                "close": round(c, 2),
                "adjClose": round(c, 2),
                "volume": int(v),
            }
        )
    rows.reverse()  # most-recent-first, as the FMP historical endpoint returns
    return rows


def dt(s):
    return date.fromisoformat(s)


# --- EXMA: gap up Oct 16, red week Oct 19-23, breakout week Nov 2-6 -> BREAKOUT
exma_knots = [(dt("2025-11-10"), 42.0), (dt("2026-09-15"), 52.0), (dt("2026-10-15"), 60.0)]
exma = {
    "2026-10-15": (59.8, 60.6, 59.4, 60.2, 2_400_000),
    "2026-10-16": (65.0, 66.5, 64.6, 66.0, 6_800_000),
    "2026-10-19": (66.2, 66.6, 65.2, 65.5, 3_000_000),
    "2026-10-20": (65.5, 65.9, 64.6, 64.8, 2_600_000),
    "2026-10-21": (64.8, 65.1, 63.9, 64.2, 2_300_000),
    "2026-10-22": (64.2, 64.6, 63.7, 64.0, 2_100_000),
    "2026-10-23": (64.0, 64.4, 63.5, 63.9, 2_000_000),
    "2026-10-26": (64.0, 64.9, 63.8, 64.7, 1_900_000),
    "2026-10-27": (64.7, 65.4, 64.5, 65.2, 1_900_000),
    "2026-10-28": (65.2, 65.8, 64.9, 65.4, 1_800_000),
    "2026-10-29": (65.4, 66.1, 65.1, 65.8, 1_900_000),
    "2026-10-30": (65.8, 66.4, 65.5, 66.0, 1_900_000),
    "2026-11-02": (66.1, 67.0, 65.9, 66.8, 2_700_000),
    "2026-11-03": (66.8, 67.8, 66.6, 67.6, 2_900_000),
    "2026-11-04": (67.6, 68.5, 67.4, 68.3, 3_000_000),
    "2026-11-05": (68.3, 69.2, 68.1, 68.9, 3_100_000),
    "2026-11-06": (68.9, 69.7, 68.7, 69.3, 3_300_000),
}

# --- EXMB: gap up Oct 23, red week Oct 26-30, recovery below red high -> SIGNAL_READY
exmb_knots = [(dt("2025-11-10"), 30.0), (dt("2026-09-15"), 36.5), (dt("2026-10-22"), 40.0)]
exmb = {
    "2026-10-22": (39.8, 40.3, 39.5, 40.0, 2_200_000),
    "2026-10-23": (42.4, 43.2, 42.1, 43.0, 5_900_000),
    "2026-10-26": (43.2, 43.4, 42.2, 42.5, 2_900_000),
    "2026-10-27": (42.5, 42.7, 41.9, 42.0, 2_400_000),
    "2026-10-28": (42.0, 42.2, 41.4, 41.6, 2_200_000),
    "2026-10-29": (41.6, 41.9, 40.9, 41.2, 2_100_000),
    "2026-10-30": (41.2, 41.5, 40.7, 41.0, 2_000_000),
    "2026-11-02": (41.2, 41.8, 41.0, 41.6, 1_900_000),
    "2026-11-03": (41.6, 42.1, 41.4, 41.9, 1_900_000),
    "2026-11-04": (41.9, 42.4, 41.7, 42.2, 1_800_000),
    "2026-11-05": (42.2, 42.6, 42.0, 42.4, 1_800_000),
    "2026-11-06": (42.4, 42.9, 42.2, 42.6, 1_900_000),
}

# --- EXMC: gap up Nov 3 before the open; only the earnings week exists -> MONITORING
exmc_knots = [(dt("2025-11-10"), 60.0), (dt("2026-09-15"), 74.0), (dt("2026-11-02"), 80.0)]
exmc = {
    "2026-11-02": (79.8, 80.4, 79.4, 80.0, 1_800_000),
    "2026-11-03": (87.2, 88.4, 86.8, 88.0, 6_200_000),
    "2026-11-04": (88.0, 89.0, 87.4, 88.6, 3_400_000),
    "2026-11-05": (88.6, 89.4, 87.9, 89.0, 2_900_000),
    "2026-11-06": (89.0, 89.8, 88.4, 89.5, 2_700_000),
}

# --- EXMD: weak reaction under a falling trend -> low grade, dropped by min grade
exmd_knots = [(dt("2025-11-10"), 52.0), (dt("2026-09-15"), 41.0), (dt("2026-10-20"), 36.0)]
exmd = {
    "2026-10-20": (35.9, 36.2, 35.5, 36.0, 1_700_000),
    "2026-10-21": (36.4, 36.6, 35.6, 35.9, 2_200_000),
    "2026-10-22": (35.9, 36.0, 35.2, 35.4, 1_800_000),
    "2026-10-23": (35.4, 35.6, 34.8, 35.0, 1_700_000),
}

# --- EXME: below the market-cap floor; filtered by the analyzer
exme_knots = [(dt("2025-11-10"), 22.0), (dt("2026-10-28"), 31.0)]
exme = {
    "2026-10-28": (30.8, 31.2, 30.4, 31.0, 400_000),
    "2026-10-29": (33.5, 34.0, 33.0, 33.8, 1_100_000),
}

SPEC = {
    "EXMA": (
        "Example Alpha Systems Inc.",
        4_800_000_000,
        "Technology",
        "Software",
        exma_knots,
        exma,
        11,
        "2026-10-15",
        "amc",
    ),
    "EXMB": (
        "Example Beta Devices Inc.",
        2_300_000_000,
        "Technology",
        "Hardware",
        exmb_knots,
        exmb,
        12,
        "2026-10-22",
        "amc",
    ),
    "EXMC": (
        "Example Gamma Health Inc.",
        6_100_000_000,
        "Healthcare",
        "Biotechnology",
        exmc_knots,
        exmc,
        13,
        "2026-11-03",
        "bmo",
    ),
    "EXMD": (
        "Example Delta Retail Inc.",
        1_900_000_000,
        "Consumer Cyclical",
        "Specialty Retail",
        exmd_knots,
        exmd,
        14,
        "2026-10-20",
        "amc",
    ),
    "EXME": (
        "Example Epsilon Micro Inc.",
        210_000_000,
        "Industrials",
        "Machinery",
        exme_knots,
        exme,
        15,
        "2026-10-28",
        "amc",
    ),
}

calendar = []
profiles = {}
prices = {}
for symbol, (name, cap, sector, industry, knots, explicit, seed, edate, time) in SPEC.items():
    prices[symbol] = build(symbol, seed, knots, explicit)
    last_close = prices[symbol][0]["close"]
    profiles[symbol] = {
        "symbol": symbol,
        "companyName": name,
        "exchange": "NASDAQ",
        "marketCap": cap,
        "price": last_close,
        "sector": sector,
        "industry": industry,
    }
    calendar.append(
        {
            "symbol": symbol,
            "date": edate,
            "time": time,
            "epsActual": None,
            "epsEstimated": None,
            "revenueActual": None,
            "revenueEstimated": None,
        }
    )

payload = {
    "description": (
        "Fictional FMP-shaped responses for the earnings-weekly offline replay. "
        "Every symbol, company, price, and volume is invented; no real market data."
    ),
    "as_of": END.isoformat(),
    "earnings_calendar": sorted(calendar, key=lambda r: (r["date"], r["symbol"])),
    "profiles": profiles,
    "prices": prices,
}


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(", ", ": "))


lines = ["{"]
lines.append(f'  "as_of": {compact(payload["as_of"])},')
lines.append(f'  "description": {compact(payload["description"])},')
lines.append('  "earnings_calendar": [')
rows = [f"    {compact(r)}" for r in payload["earnings_calendar"]]
lines.append(",\n".join(rows))
lines.append("  ],")
lines.append(
    f'  "profiles": {json.dumps(payload["profiles"], indent=2, sort_keys=True).replace(chr(10), chr(10) + "  ")},'
)
lines.append('  "prices": {')
blocks = []
for symbol in sorted(payload["prices"]):
    body = ",\n".join(f"      {compact(r)}" for r in payload["prices"][symbol])
    blocks.append(f'    "{symbol}": [\n{body}\n    ]')
lines.append(",\n".join(blocks))
lines.append("  }")
lines.append("}")
text = "\n".join(lines) + "\n"
json.loads(text)  # must stay valid JSON
with open(sys.argv[1], "w", encoding="utf-8", newline="\n") as handle:
    handle.write(text)
