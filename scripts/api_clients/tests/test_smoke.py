"""Smoke tests — hit each provider's cheapest endpoint to verify keys work.

Run:
    python3 scripts/api_clients/tests/test_smoke.py

Each provider is independent; one failure does not abort the others.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the package importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root

from scripts.api_clients.bea_client import BEAClient  # noqa: E402
from scripts.api_clients.commodity_client import CommodityClient  # noqa: E402
from scripts.api_clients.eia_client import EIAClient  # noqa: E402
from scripts.api_clients.estat_client import EStatClient  # noqa: E402
from scripts.api_clients.finnhub_client import FinnhubClient  # noqa: E402
from scripts.api_clients.news_client import NewsClient  # noqa: E402
from scripts.api_clients.polygon_client import PolygonClient  # noqa: E402
from scripts.api_clients.polymarket_client import PolymarketClient  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def _redact_query_params(msg: str) -> str:
    """Remove sensitive query-param values from error messages.

    SECURITY: requests.HTTPError stringifies to include the full request URL,
    and our clients ride keys in the query string (apiKey=, api_key=,
    access_key=, token=, appId=, registrationkey=). A 401/403 from any
    provider could echo the key into stdout/CI logs without this scrubber.
    """
    import re

    sensitive_params = (
        "apikey",
        "api_key",
        "access_key",
        "token",
        "appid",
        "registrationkey",
        "key",
        "userid",
    )
    pattern = re.compile(
        r"\b(" + "|".join(sensitive_params) + r")=[^&\s'\"\\]+",
        re.IGNORECASE,
    )
    return pattern.sub(r"\1=***REDACTED***", msg)


def check(name: str, fn) -> None:
    try:
        out = fn()
        RESULTS.append((name, True, out))
        print(f"✓ {name:25s}  {out}")
    except Exception as e:
        # SECURITY: scrub any key=value pair that might appear in the error
        msg = _redact_query_params(repr(e))[:200]
        RESULTS.append((name, False, msg))
        print(f"✗ {name:25s}  {msg}")


def smoke_polygon():
    c = PolygonClient(rate_limit_sec=13)  # 5 req/min on free tier => 12s spacing
    status = c.get_market_status()
    return f"market={status.get('market', 'unknown')}"


def smoke_polygon_aggs():
    c = PolygonClient(rate_limit_sec=13)
    bars = c.get_aggs("AAPL", "day", "2026-05-01", "2026-05-26")
    return f"{len(bars)} AAPL bars, last close=${bars[-1].close if bars else 'n/a'}"


def smoke_news():
    c = NewsClient()
    items = c.search_news("Nvidia", days=3, limit=5)
    return f"{len(items)} articles (providers={set(i.provider for i in items)})"


def smoke_eia():
    c = EIAClient()
    pjm = c.electricity_demand("PJM", days=2)
    return f"PJM {len(pjm)} demand points, last={pjm[-1].value if pjm else 'n/a'} {pjm[-1].unit if pjm else ''}"


def smoke_eia_gas():
    c = EIAClient()
    gas = c.natural_gas_spot(days=5)
    return f"Henry Hub {len(gas)} points, latest=${gas[-1].value if gas else 'n/a'}/MMBtu"


def smoke_polymarket():
    c = PolymarketClient()
    markets = c.get_top_markets_by_volume(limit=5)
    return f"{len(markets)} top markets, leader='{markets[0].question[:60] if markets else 'n/a'}'"


def smoke_finnhub_econ():
    c = FinnhubClient()
    evs = c.economic_calendar()
    return f"{len(evs)} economic events (next 7 days)"


def smoke_finnhub_earnings():
    c = FinnhubClient()
    evs = c.earnings_calendar()
    return f"{len(evs)} earnings reports (next 7 days)"


def smoke_bea():
    c = BEAClient()
    obs = c.real_gdp_growth()  # auto-computes last-N years with publication lag
    if not obs:
        return "no observations returned"
    latest = obs[-1]
    return f"{len(obs)} GDP-growth points, latest {latest.time_period} = {latest.value}"


def smoke_commodity():
    c = CommodityClient()
    prices = c.latest(["BRENT", "GOLD"])
    if not prices:
        return "no prices returned"
    parts = [f"{p.common_name}=${p.usd_price:.2f}/{p.unit}" for p in prices]
    return ", ".join(parts)


def smoke_estat():
    c = EStatClient()
    obs = c.cpi_national(limit=3)
    if not obs:
        return "no observations returned"
    latest = obs[-1]
    return f"{len(obs)} JP CPI rows, latest {latest.time_period} = {latest.value}"


def main() -> int:
    print("=" * 70)
    print("API smoke tests")
    print("=" * 70)
    check("Polygon: market status", smoke_polygon)
    check("Polygon: AAPL aggs", smoke_polygon_aggs)
    check("News (Marketaux+Newsdata)", smoke_news)
    check("EIA: PJM demand", smoke_eia)
    check("EIA: Henry Hub gas", smoke_eia_gas)
    check("Polymarket: top markets", smoke_polymarket)
    check("Finnhub: econ calendar", smoke_finnhub_econ)
    check("Finnhub: earnings cal", smoke_finnhub_earnings)
    check("BEA: real GDP growth", smoke_bea)
    check("Commodity: Brent+Gold", smoke_commodity)
    check("e-Stat: Japan CPI", smoke_estat)
    print("=" * 70)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"{passed}/{len(RESULTS)} providers reachable")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
