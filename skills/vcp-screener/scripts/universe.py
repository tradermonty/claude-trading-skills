#!/usr/bin/env python3
"""
Curated starter universe of ~100 liquid U.S. stocks for the VCP screener.

Organised by GICS sector. MA and V are classified under Financials
(GICS: Data Processing & Outsourced Services within Financials sector).

Use validate_universe() to assert integrity in tests.
"""

from __future__ import annotations

STARTER_UNIVERSE: list[dict] = [
    # ── Information Technology (18) ────────────────────────────────────────
    {"symbol": "AAPL",  "name": "Apple Inc.",                        "sector": "Information Technology"},
    {"symbol": "MSFT",  "name": "Microsoft Corporation",             "sector": "Information Technology"},
    {"symbol": "NVDA",  "name": "NVIDIA Corporation",                "sector": "Information Technology"},
    {"symbol": "AVGO",  "name": "Broadcom Inc.",                     "sector": "Information Technology"},
    {"symbol": "AMD",   "name": "Advanced Micro Devices",            "sector": "Information Technology"},
    {"symbol": "QCOM",  "name": "Qualcomm Inc.",                     "sector": "Information Technology"},
    {"symbol": "INTC",  "name": "Intel Corporation",                 "sector": "Information Technology"},
    {"symbol": "ORCL",  "name": "Oracle Corporation",                "sector": "Information Technology"},
    {"symbol": "CRM",   "name": "Salesforce Inc.",                   "sector": "Information Technology"},
    {"symbol": "ADBE",  "name": "Adobe Inc.",                        "sector": "Information Technology"},
    {"symbol": "INTU",  "name": "Intuit Inc.",                       "sector": "Information Technology"},
    {"symbol": "TXN",   "name": "Texas Instruments",                 "sector": "Information Technology"},
    {"symbol": "MU",    "name": "Micron Technology",                 "sector": "Information Technology"},
    {"symbol": "KLAC",  "name": "KLA Corporation",                   "sector": "Information Technology"},
    {"symbol": "LRCX",  "name": "Lam Research Corporation",          "sector": "Information Technology"},
    {"symbol": "AMAT",  "name": "Applied Materials Inc.",            "sector": "Information Technology"},
    {"symbol": "PANW",  "name": "Palo Alto Networks",                "sector": "Information Technology"},
    {"symbol": "SNPS",  "name": "Synopsys Inc.",                     "sector": "Information Technology"},
    # ── Communication Services (8) ─────────────────────────────────────────
    {"symbol": "GOOGL", "name": "Alphabet Inc. Class A",             "sector": "Communication Services"},
    {"symbol": "META",  "name": "Meta Platforms Inc.",               "sector": "Communication Services"},
    {"symbol": "NFLX",  "name": "Netflix Inc.",                      "sector": "Communication Services"},
    {"symbol": "DIS",   "name": "The Walt Disney Company",           "sector": "Communication Services"},
    {"symbol": "T",     "name": "AT&T Inc.",                         "sector": "Communication Services"},
    {"symbol": "VZ",    "name": "Verizon Communications",            "sector": "Communication Services"},
    {"symbol": "CMCSA", "name": "Comcast Corporation",               "sector": "Communication Services"},
    {"symbol": "CHTR",  "name": "Charter Communications",            "sector": "Communication Services"},
    # ── Consumer Discretionary (10) ────────────────────────────────────────
    {"symbol": "AMZN",  "name": "Amazon.com Inc.",                   "sector": "Consumer Discretionary"},
    {"symbol": "TSLA",  "name": "Tesla Inc.",                        "sector": "Consumer Discretionary"},
    {"symbol": "HD",    "name": "The Home Depot Inc.",               "sector": "Consumer Discretionary"},
    {"symbol": "LOW",   "name": "Lowe's Companies Inc.",             "sector": "Consumer Discretionary"},
    {"symbol": "TJX",   "name": "TJX Companies Inc.",                "sector": "Consumer Discretionary"},
    {"symbol": "SBUX",  "name": "Starbucks Corporation",             "sector": "Consumer Discretionary"},
    {"symbol": "MCD",   "name": "McDonald's Corporation",            "sector": "Consumer Discretionary"},
    {"symbol": "NKE",   "name": "Nike Inc.",                         "sector": "Consumer Discretionary"},
    {"symbol": "BKNG",  "name": "Booking Holdings Inc.",             "sector": "Consumer Discretionary"},
    {"symbol": "GM",    "name": "General Motors Company",            "sector": "Consumer Discretionary"},
    # ── Consumer Staples (8) ───────────────────────────────────────────────
    {"symbol": "PG",    "name": "Procter & Gamble Co.",              "sector": "Consumer Staples"},
    {"symbol": "KO",    "name": "The Coca-Cola Company",             "sector": "Consumer Staples"},
    {"symbol": "PEP",   "name": "PepsiCo Inc.",                      "sector": "Consumer Staples"},
    {"symbol": "WMT",   "name": "Walmart Inc.",                      "sector": "Consumer Staples"},
    {"symbol": "COST",  "name": "Costco Wholesale Corporation",      "sector": "Consumer Staples"},
    {"symbol": "PM",    "name": "Philip Morris International",       "sector": "Consumer Staples"},
    {"symbol": "MO",    "name": "Altria Group Inc.",                 "sector": "Consumer Staples"},
    {"symbol": "CL",    "name": "Colgate-Palmolive Company",         "sector": "Consumer Staples"},
    # ── Health Care (12) ───────────────────────────────────────────────────
    {"symbol": "UNH",   "name": "UnitedHealth Group Inc.",           "sector": "Health Care"},
    {"symbol": "JNJ",   "name": "Johnson & Johnson",                 "sector": "Health Care"},
    {"symbol": "LLY",   "name": "Eli Lilly and Company",             "sector": "Health Care"},
    {"symbol": "ABBV",  "name": "AbbVie Inc.",                       "sector": "Health Care"},
    {"symbol": "MRK",   "name": "Merck & Co. Inc.",                  "sector": "Health Care"},
    {"symbol": "TMO",   "name": "Thermo Fisher Scientific",          "sector": "Health Care"},
    {"symbol": "ABT",   "name": "Abbott Laboratories",               "sector": "Health Care"},
    {"symbol": "DHR",   "name": "Danaher Corporation",               "sector": "Health Care"},
    {"symbol": "BMY",   "name": "Bristol-Myers Squibb",              "sector": "Health Care"},
    {"symbol": "AMGN",  "name": "Amgen Inc.",                        "sector": "Health Care"},
    {"symbol": "ISRG",  "name": "Intuitive Surgical Inc.",           "sector": "Health Care"},
    {"symbol": "CVS",   "name": "CVS Health Corporation",            "sector": "Health Care"},
    # ── Financials (12) ────────────────────────────────────────────────────
    {"symbol": "JPM",   "name": "JPMorgan Chase & Co.",              "sector": "Financials"},
    {"symbol": "BAC",   "name": "Bank of America Corp.",             "sector": "Financials"},
    {"symbol": "WFC",   "name": "Wells Fargo & Company",             "sector": "Financials"},
    {"symbol": "GS",    "name": "The Goldman Sachs Group",           "sector": "Financials"},
    {"symbol": "MS",    "name": "Morgan Stanley",                    "sector": "Financials"},
    {"symbol": "BLK",   "name": "BlackRock Inc.",                    "sector": "Financials"},
    {"symbol": "AXP",   "name": "American Express Company",          "sector": "Financials"},
    {"symbol": "SPGI",  "name": "S&P Global Inc.",                   "sector": "Financials"},
    {"symbol": "MA",    "name": "Mastercard Incorporated",           "sector": "Financials"},
    {"symbol": "V",     "name": "Visa Inc.",                         "sector": "Financials"},
    {"symbol": "C",     "name": "Citigroup Inc.",                    "sector": "Financials"},
    {"symbol": "USB",   "name": "U.S. Bancorp",                      "sector": "Financials"},
    # ── Industrials (10) ───────────────────────────────────────────────────
    {"symbol": "CAT",   "name": "Caterpillar Inc.",                  "sector": "Industrials"},
    {"symbol": "DE",    "name": "Deere & Company",                   "sector": "Industrials"},
    {"symbol": "HON",   "name": "Honeywell International",           "sector": "Industrials"},
    {"symbol": "GE",    "name": "GE Aerospace",                      "sector": "Industrials"},
    {"symbol": "BA",    "name": "The Boeing Company",                "sector": "Industrials"},
    {"symbol": "UPS",   "name": "United Parcel Service",             "sector": "Industrials"},
    {"symbol": "FDX",   "name": "FedEx Corporation",                 "sector": "Industrials"},
    {"symbol": "MMM",   "name": "3M Company",                        "sector": "Industrials"},
    {"symbol": "LMT",   "name": "Lockheed Martin Corporation",       "sector": "Industrials"},
    {"symbol": "RTX",   "name": "RTX Corporation",                   "sector": "Industrials"},
    # ── Energy (7) ────────────────────────────────────────────────────────
    {"symbol": "XOM",   "name": "Exxon Mobil Corporation",           "sector": "Energy"},
    {"symbol": "CVX",   "name": "Chevron Corporation",               "sector": "Energy"},
    {"symbol": "COP",   "name": "ConocoPhillips",                    "sector": "Energy"},
    {"symbol": "SLB",   "name": "SLB (Schlumberger)",                "sector": "Energy"},
    {"symbol": "EOG",   "name": "EOG Resources Inc.",                "sector": "Energy"},
    {"symbol": "PSX",   "name": "Phillips 66",                       "sector": "Energy"},
    {"symbol": "OXY",   "name": "Occidental Petroleum",              "sector": "Energy"},
    # ── Materials (5) ─────────────────────────────────────────────────────
    {"symbol": "LIN",   "name": "Linde plc",                         "sector": "Materials"},
    {"symbol": "APD",   "name": "Air Products and Chemicals",        "sector": "Materials"},
    {"symbol": "SHW",   "name": "The Sherwin-Williams Company",      "sector": "Materials"},
    {"symbol": "ECL",   "name": "Ecolab Inc.",                       "sector": "Materials"},
    {"symbol": "FCX",   "name": "Freeport-McMoRan Inc.",             "sector": "Materials"},
    # ── Real Estate (5) ───────────────────────────────────────────────────
    {"symbol": "AMT",   "name": "American Tower Corporation",        "sector": "Real Estate"},
    {"symbol": "PLD",   "name": "Prologis Inc.",                     "sector": "Real Estate"},
    {"symbol": "CCI",   "name": "Crown Castle Inc.",                 "sector": "Real Estate"},
    {"symbol": "EQIX",  "name": "Equinix Inc.",                      "sector": "Real Estate"},
    {"symbol": "SPG",   "name": "Simon Property Group",              "sector": "Real Estate"},
    # ── Utilities (5) ─────────────────────────────────────────────────────
    {"symbol": "NEE",   "name": "NextEra Energy Inc.",               "sector": "Utilities"},
    {"symbol": "DUK",   "name": "Duke Energy Corporation",           "sector": "Utilities"},
    {"symbol": "SO",    "name": "The Southern Company",              "sector": "Utilities"},
    {"symbol": "AEP",   "name": "American Electric Power",           "sector": "Utilities"},
    {"symbol": "EXC",   "name": "Exelon Corporation",                "sector": "Utilities"},
]

# Fast symbol → sector lookup
SECTOR_MAP: dict[str, str] = {e["symbol"]: e["sector"] for e in STARTER_UNIVERSE}

# Fast symbol → name lookup
NAME_MAP: dict[str, str] = {e["symbol"]: e["name"] for e in STARTER_UNIVERSE}


def validate_universe(universe: list[dict] | None = None) -> list[str]:
    """Return a list of validation error strings (empty = clean).

    Checks performed:
    - No duplicate ticker symbols
    - No empty / whitespace-only ticker strings
    - No blank sector labels
    - All entries have 'symbol', 'name', 'sector' keys
    """
    if universe is None:
        universe = STARTER_UNIVERSE

    errors: list[str] = []
    seen: set[str] = set()

    for i, entry in enumerate(universe):
        for key in ("symbol", "name", "sector"):
            if key not in entry:
                errors.append(f"Entry[{i}] missing key '{key}': {entry}")

        sym = entry.get("symbol", "")
        if not isinstance(sym, str) or not sym.strip():
            errors.append(f"Entry[{i}] has empty/invalid symbol: {repr(sym)}")
            continue

        sym = sym.strip()
        if sym in seen:
            errors.append(f"Duplicate ticker: {sym}")
        seen.add(sym)

        sector = entry.get("sector", "")
        if not isinstance(sector, str) or not sector.strip():
            errors.append(f"Entry[{i}] ({sym}) has empty/invalid sector: {repr(sector)}")

    return errors
