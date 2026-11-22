"""FMP /stable migration for theme-detector.

Keys issued after 2025-08-31 lose v3 access (403). Fixes:
- Quotes/history are fetched one symbol per request (FMP /stable does not
  support comma-batched symbols — that silently returns []).
- Historical uses /stable/historical-price-eod/full (the prior stable URL,
  historical-price-full, 404s) with timeseries->from/to and flat-list
  normalization back to the v3 {"symbol","historical"} shape.
- ETF holdings: /api/v3/etf-holder/{sym} -> /stable/etf/holdings?symbol=
  (+ v3 fallback); both expose `asset` and `marketValue`.
"""

from unittest.mock import MagicMock, patch

import representative_stock_selector as rss
from etf_scanner import ETFScanner, _normalize_eod_flat_list, _stable_hist_url


class TestHistoricalNormalize:
    def test_flat_list_to_v3_dict(self):
        flat = [
            {"symbol": "AAPL", "date": "2026-05-19", "close": 298.97},
            {"symbol": "AAPL", "date": "2026-05-18", "close": 296.0},
        ]
        out = _normalize_eod_flat_list(flat, "AAPL")
        assert out["symbol"] == "AAPL"
        assert len(out["historical"]) == 2

    def test_no_match_returns_none(self):
        assert _normalize_eod_flat_list([{"symbol": "MSFT", "close": 1}], "AAPL") is None

    def test_dict_passthrough(self):
        d = {"symbol": "AAPL", "historical": [{"close": 1}]}
        assert _normalize_eod_flat_list(d, "AAPL") is d

    def test_stable_hist_url_converts_timeseries(self):
        base = "https://financialmodelingprep.com/stable/historical-price-eod/full"
        url, params = _stable_hist_url(base, "AAPL", {"timeseries": 20})
        assert url == base
        assert params["symbol"] == "AAPL"
        assert "from" in params and "to" in params
        assert "timeseries" not in params  # converted to a from/to range


class TestDeBatch:
    def test_batch_sizes_are_one(self):
        assert ETFScanner.FMP_QUOTE_BATCH_SIZE == 1
        assert ETFScanner.FMP_HIST_BATCH_SIZE == 1

    def test_quotes_fetched_one_symbol_per_request(self):
        scanner = ETFScanner(fmp_api_key="k")
        seen = []

        def fake_req(endpoint_key, symbols_str, extra_params=None):
            seen.append((endpoint_key, symbols_str))
            return [{"symbol": symbols_str, "price": 100.0}]

        scanner._fmp_request = fake_req
        scanner._fetch_fmp_quotes(["AAPL", "MSFT", "NVDA"])
        quote_syms = [s for e, s in seen if e == "quote"]
        assert all("," not in s for s in quote_syms)  # never comma-batched
        assert set(quote_syms) >= {"AAPL", "MSFT", "NVDA"}


class TestEtfHoldings:
    def _resp(self, status, payload):
        r = MagicMock()
        r.status_code = status
        r.json.return_value = payload
        return r

    def test_stable_etf_holdings_first(self):
        sel = rss.RepresentativeStockSelector(fmp_api_key="k")
        sel._rate_limit = lambda: None
        with patch("requests.Session") as factory:
            factory.return_value.get.return_value = self._resp(
                200, [{"asset": "NVDA", "marketValue": 1_000_000_000}]
            )
            holds = sel._fetch_etf_holdings("SPY", limit=5)
        assert holds[0]["symbol"] == "NVDA"
        call = factory.return_value.get.call_args
        assert call.args[0].endswith("/stable/etf/holdings")
        assert call.kwargs["params"] == {"symbol": "SPY", "apikey": "k"}
        factory.return_value.close.assert_called_once()

    def test_denied_holdings_has_no_legacy_fallback(self):
        sel = rss.RepresentativeStockSelector(fmp_api_key="k")
        sel._rate_limit = lambda: None
        with patch("requests.Session") as factory:
            factory.return_value.get.return_value = self._resp(403, {})
            assert sel._fetch_etf_holdings("XLK", limit=5) == []
        assert factory.return_value.get.call_count == 1
        assert factory.return_value.get.call_args.args[0].endswith("/stable/etf/holdings")
