"""Shared, keyless CoinGecko response boundaries (stdlib only).

These checks establish shape/numeric/order validity, not completeness, freshness,
point-in-time availability or the accuracy of market observations.
"""

import math


class PayloadError(ValueError):
    """Fixed diagnostics only; never include provider values or response bodies."""


def _positive_number(value, code):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PayloadError(code)
    try:
        valid = math.isfinite(value) and value > 0
    except OverflowError:
        valid = False
    if not valid:
        raise PayloadError(code)
    return value


def dominance_value(value):
    value = _positive_number(value, "COINGECKO_GLOBAL_INVALID_DOMINANCE")
    if value > 100:
        raise PayloadError("COINGECKO_GLOBAL_INVALID_DOMINANCE")
    return value


def global_rows(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise PayloadError("COINGECKO_GLOBAL_INVALID_SHAPE")
    shares = payload["data"].get("market_cap_percentage")
    if not isinstance(shares, dict) or "btc" not in shares:
        raise PayloadError("COINGECKO_GLOBAL_MISSING_BTC")
    return [{"btc_dominance": dominance_value(shares["btc"])}]


def market_chart_rows(payload):
    if not isinstance(payload, dict):
        raise PayloadError("COINGECKO_MARKET_CHART_INVALID_SHAPE")
    prices = payload.get("prices")
    if not isinstance(prices, list) or not prices:
        raise PayloadError("COINGECKO_MARKET_CHART_INVALID_PRICES")
    rows = []
    previous = None
    for pair in prices:
        if not isinstance(pair, list) or len(pair) != 2:
            raise PayloadError("COINGECKO_MARKET_CHART_INVALID_PAIR")
        timestamp = _positive_number(pair[0], "COINGECKO_MARKET_CHART_INVALID_TIMESTAMP")
        price = _positive_number(pair[1], "COINGECKO_MARKET_CHART_INVALID_PRICE")
        if previous is not None and timestamp <= previous:
            raise PayloadError("COINGECKO_MARKET_CHART_UNORDERED_TIMESTAMPS")
        rows.append({"timestamp_ms": timestamp, "price": price})
        previous = timestamp
    return rows


def cached_closes(values):
    # Legacy close-only caches carry no timestamps. Do not invent date evidence.
    if not isinstance(values, list) or not values:
        raise PayloadError("COINGECKO_MARKET_CHART_INVALID_CACHE")
    for value in values:
        _positive_number(value, "COINGECKO_MARKET_CHART_INVALID_CACHE")
    return values
