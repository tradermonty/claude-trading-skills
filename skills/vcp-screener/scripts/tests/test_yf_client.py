"""Tests for YFinanceClient (yf_client.py).

Covers:
- auto_adjust=False is always passed to yf.download()
- Both Close and Adj Close are preserved in output dicts
- Adj Close differs from Close when the mock DataFrame says so
- Retry on missing symbol: succeeds on second attempt
- Retry exhausted: symbol logged in skipped list
- Skipped dict has required keys
- Cache reuse: yf.download() called only once for same args
- Backoff delays are applied between retries
"""

from __future__ import annotations

import sys
import os
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from yf_client import YFinanceClient, _df_to_hist, _derive_quote, RETRY_DELAYS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv_df(
    symbol: str,
    n: int = 5,
    close: float = 100.0,
    adj_close: float | None = None,
    multi: bool = True,
) -> pd.DataFrame:
    """Build a minimal yfinance-style DataFrame.

    When multi=True, columns are a MultiIndex (ticker, field) matching the
    real yf.download() output with group_by='ticker': level-0 = ticker,
    level-1 = field. When multi=False, columns are flat (single-ticker string
    download format).
    """
    dates = pd.date_range("2026-01-01", periods=n, freq="B")
    adj = adj_close if adj_close is not None else close

    data = {
        "Open":      [close * 0.99] * n,
        "High":      [close * 1.01] * n,
        "Low":       [close * 0.98] * n,
        "Close":     [close] * n,
        "Adj Close": [adj] * n,
        "Volume":    [1_000_000] * n,
    }
    df = pd.DataFrame(data, index=dates)

    if multi:
        # Real yfinance group_by='ticker' layout: ticker at level-0, field at level-1
        df.columns = pd.MultiIndex.from_tuples(
            [(symbol, col) for col in df.columns],
            names=["ticker", "field"],
        )
    return df


def _make_empty_df() -> pd.DataFrame:
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# 1. auto_adjust=False always passed
# ---------------------------------------------------------------------------

class TestAutoAdjustFalse:
    def test_auto_adjust_false_single_symbol(self):
        """yf.download must receive auto_adjust=False for a single symbol."""
        client = YFinanceClient()
        mock_df = _make_ohlcv_df("AAPL", multi=False)

        with patch("yf_client.yf.download", return_value=mock_df) as mock_dl:
            client.bulk_download(["AAPL"], period="1y")

        _, kwargs = mock_dl.call_args
        assert kwargs.get("auto_adjust") is False, (
            "auto_adjust must be explicitly False"
        )

    def test_auto_adjust_false_multi_symbol(self):
        """yf.download must receive auto_adjust=False for multiple symbols."""
        client = YFinanceClient()
        syms = ["AAPL", "MSFT"]
        dfs = {sym: _make_ohlcv_df(sym) for sym in syms}
        combined = pd.concat(dfs.values(), axis=1)

        with patch("yf_client.yf.download", return_value=combined) as mock_dl:
            client.bulk_download(syms, period="1y")

        _, kwargs = mock_dl.call_args
        assert kwargs.get("auto_adjust") is False


# ---------------------------------------------------------------------------
# 2. Close and Adj Close both preserved
# ---------------------------------------------------------------------------

class TestCloseAndAdjClosePreserved:
    def test_both_keys_present_single(self):
        """Output dicts must have 'close' and 'adjClose' keys."""
        client = YFinanceClient()
        df = _make_ohlcv_df("AAPL", multi=False)

        with patch("yf_client.yf.download", return_value=df):
            result = client.bulk_download(["AAPL"])

        hist = result.get("AAPL", [])
        assert hist, "Expected non-empty history for AAPL"
        row = hist[0]
        assert "close" in row
        assert "adjClose" in row

    def test_adj_close_matches_close_when_same(self):
        """When Adj Close == Close (no dividends/splits), both values are equal."""
        client = YFinanceClient()
        df = _make_ohlcv_df("MSFT", close=300.0, adj_close=300.0, multi=False)

        with patch("yf_client.yf.download", return_value=df):
            result = client.bulk_download(["MSFT"])

        hist = result["MSFT"]
        assert hist[0]["close"] == pytest.approx(300.0)
        assert hist[0]["adjClose"] == pytest.approx(300.0)

    def test_adj_close_differs_when_dividend(self):
        """When Adj Close != Close (dividend adjusted), both values are distinct."""
        client = YFinanceClient()
        # Simulate a stock with a recent dividend: adj_close < close
        df = _make_ohlcv_df("JNJ", close=160.0, adj_close=155.5, multi=False)

        with patch("yf_client.yf.download", return_value=df):
            result = client.bulk_download(["JNJ"])

        hist = result["JNJ"]
        assert hist[0]["close"] == pytest.approx(160.0)
        assert hist[0]["adjClose"] == pytest.approx(155.5)
        assert hist[0]["adjClose"] != hist[0]["close"]


# ---------------------------------------------------------------------------
# 3. Retry on missing symbol
# ---------------------------------------------------------------------------

class TestRetryOnMissingSymbol:
    def test_retry_succeeds_on_second_attempt(self):
        """Symbol with empty first download is retried and succeeds; not skipped."""
        client = YFinanceClient()
        good_df = _make_ohlcv_df("NVDA", multi=False)

        call_count = [0]

        def fake_download(**kwargs):
            call_count[0] += 1
            tickers = kwargs.get("tickers", [])
            syms = [tickers] if isinstance(tickers, str) else list(tickers)
            if "NVDA" in syms and call_count[0] == 1:
                # First call (bulk): return empty → triggers retry
                return _make_empty_df()
            # Second call (individual retry): return good data
            return good_df

        with patch("yf_client.yf.download", side_effect=fake_download):
            with patch("yf_client.time.sleep"):   # skip real delays
                result = client.bulk_download(["NVDA"])

        assert result.get("NVDA"), "NVDA should be recovered after retry"
        skipped = client.get_skipped_symbols()
        assert not any(s["symbol"] == "NVDA" for s in skipped), (
            "Successfully retried symbol must not appear in skipped list"
        )

    def test_retry_count_incremented(self):
        """_retries_attempted is incremented for each retry attempt."""
        client = YFinanceClient()
        good_df = _make_ohlcv_df("AMD", multi=False)
        call_count = [0]

        def fake_download(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_empty_df()
            return good_df

        with patch("yf_client.yf.download", side_effect=fake_download):
            with patch("yf_client.time.sleep"):
                client.bulk_download(["AMD"])

        assert client._retries_attempted >= 1


# ---------------------------------------------------------------------------
# 4. Retry exhausted → symbol logged as skipped
# ---------------------------------------------------------------------------

class TestRetryExhausted:
    def test_symbol_in_skipped_after_all_retries_fail(self):
        """Symbol that is empty after all retries appears in get_skipped_symbols()."""
        client = YFinanceClient()

        with patch("yf_client.yf.download", return_value=_make_empty_df()):
            with patch("yf_client.time.sleep"):
                result = client.bulk_download(["BADTICKER"])

        assert not result.get("BADTICKER"), "Failed symbol should have no history"
        skipped = client.get_skipped_symbols()
        assert any(s["symbol"] == "BADTICKER" for s in skipped), (
            "Exhausted symbol must appear in skipped list"
        )

    def test_good_symbols_not_in_skipped(self):
        """Successful symbols must not appear in the skipped list."""
        client = YFinanceClient()
        good_df = _make_ohlcv_df("AAPL", multi=False)

        with patch("yf_client.yf.download", return_value=good_df):
            client.bulk_download(["AAPL"])

        skipped = client.get_skipped_symbols()
        assert not any(s["symbol"] == "AAPL" for s in skipped)


# ---------------------------------------------------------------------------
# 5. Skipped dict format
# ---------------------------------------------------------------------------

class TestSkippedDictFormat:
    def test_skipped_entry_has_required_keys(self):
        """Skipped entry must have symbol, http_status, error_category, endpoint."""
        client = YFinanceClient()

        with patch("yf_client.yf.download", return_value=_make_empty_df()):
            with patch("yf_client.time.sleep"):
                client.bulk_download(["GHOST"])

        skipped = client.get_skipped_symbols()
        assert skipped, "Expected at least one skipped entry"
        entry = skipped[0]
        assert "symbol" in entry
        assert "http_status" in entry
        assert "error_category" in entry
        assert "endpoint" in entry

    def test_skipped_error_category_value(self):
        """error_category for a failed yfinance download should be 'yf_download_failed'."""
        client = YFinanceClient()

        with patch("yf_client.yf.download", return_value=_make_empty_df()):
            with patch("yf_client.time.sleep"):
                client.bulk_download(["GHOST"])

        skipped = client.get_skipped_symbols()
        entry = next(s for s in skipped if s["symbol"] == "GHOST")
        assert entry["error_category"] == "yf_download_failed"

    def test_get_skipped_symbols_returns_copy(self):
        """Mutating the returned list must not affect internal state."""
        client = YFinanceClient()

        with patch("yf_client.yf.download", return_value=_make_empty_df()):
            with patch("yf_client.time.sleep"):
                client.bulk_download(["GHOST"])

        returned = client.get_skipped_symbols()
        returned.clear()
        assert len(client.get_skipped_symbols()) == 1


# ---------------------------------------------------------------------------
# 6. Cache reuse
# ---------------------------------------------------------------------------

class TestCacheReuse:
    def test_second_call_hits_cache(self):
        """yf.download called exactly once when bulk_download is called twice with same args."""
        client = YFinanceClient()
        df = _make_ohlcv_df("AAPL", multi=False)

        with patch("yf_client.yf.download", return_value=df) as mock_dl:
            client.bulk_download(["AAPL"], period="1y")
            client.bulk_download(["AAPL"], period="1y")

        assert mock_dl.call_count == 1, (
            "yf.download should be called only once; second call uses cache"
        )

    def test_cache_hit_counter_incremented(self):
        """_cache_hits is incremented on a cache hit."""
        client = YFinanceClient()
        df = _make_ohlcv_df("MSFT", multi=False)

        with patch("yf_client.yf.download", return_value=df):
            client.bulk_download(["MSFT"])
            client.bulk_download(["MSFT"])

        assert client._cache_hits == 1

    def test_different_period_not_cached(self):
        """Different period strings are treated as separate cache entries."""
        client = YFinanceClient()
        df = _make_ohlcv_df("AAPL", multi=False)

        with patch("yf_client.yf.download", return_value=df) as mock_dl:
            client.bulk_download(["AAPL"], period="1y")
            client.bulk_download(["AAPL"], period="6mo")

        assert mock_dl.call_count == 2


# ---------------------------------------------------------------------------
# 7. Backoff delays
# ---------------------------------------------------------------------------

class TestBackoffDelays:
    def test_sleep_called_with_retry_delays(self):
        """time.sleep is called with values from RETRY_DELAYS during retries."""
        client = YFinanceClient()
        good_df = _make_ohlcv_df("TSLA", multi=False)
        call_count = [0]

        def fake_download(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_empty_df()  # force retry
            return good_df

        with patch("yf_client.yf.download", side_effect=fake_download):
            with patch("yf_client.time.sleep") as mock_sleep:
                client.bulk_download(["TSLA"])

        sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
        # First retry sleep should be RETRY_DELAYS[0]
        assert sleep_args[0] == RETRY_DELAYS[0], (
            f"First retry delay should be {RETRY_DELAYS[0]}s, got {sleep_args[0]}s"
        )

    def test_no_sleep_when_no_retry_needed(self):
        """time.sleep is not called when all symbols download successfully."""
        client = YFinanceClient()
        df = _make_ohlcv_df("AAPL", multi=False)

        with patch("yf_client.yf.download", return_value=df):
            with patch("yf_client.time.sleep") as mock_sleep:
                client.bulk_download(["AAPL"])

        assert mock_sleep.call_count == 0


# ---------------------------------------------------------------------------
# 8. _df_to_hist unit tests
# ---------------------------------------------------------------------------

class TestDfToHist:
    def test_empty_df_returns_empty_list(self):
        assert _df_to_hist(_make_empty_df(), "AAPL") == []

    def test_none_returns_empty_list(self):
        assert _df_to_hist(None, "AAPL") == []

    def test_most_recent_first(self):
        """Output must be most-recent-first (yfinance returns oldest-first)."""
        df = _make_ohlcv_df("AAPL", n=3, multi=False)
        hist = _df_to_hist(df, "AAPL")
        assert len(hist) == 3
        # Dates should be in descending order
        dates = [h["date"] for h in hist]
        assert dates == sorted(dates, reverse=True)

    def test_standard_keys_present(self):
        df = _make_ohlcv_df("MSFT", multi=False)
        hist = _df_to_hist(df, "MSFT")
        row = hist[0]
        for key in ("date", "open", "high", "low", "close", "adjClose", "volume"):
            assert key in row, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# 9. _derive_quote unit tests
# ---------------------------------------------------------------------------

class TestDeriveQuote:
    def _make_hist(self, n=30, close=100.0, high=105.0, low=95.0, volume=1_000_000):
        return [
            {"date": f"2026-01-{i+1:02d}", "open": close, "high": high,
             "low": low, "close": close, "adjClose": close, "volume": volume}
            for i in range(n)
        ]

    def test_price_is_most_recent_close(self):
        hist = self._make_hist(close=150.0)
        q = _derive_quote("AAPL", hist)
        assert q["price"] == pytest.approx(150.0)

    def test_year_high_from_hist(self):
        hist = self._make_hist(high=200.0)
        q = _derive_quote("AAPL", hist)
        assert q["yearHigh"] == pytest.approx(200.0)

    def test_year_low_from_hist(self):
        hist = self._make_hist(low=80.0)
        q = _derive_quote("AAPL", hist)
        assert q["yearLow"] == pytest.approx(80.0)

    def test_avg_volume_from_recent_bars(self):
        hist = self._make_hist(volume=500_000)
        q = _derive_quote("AAPL", hist)
        assert q["avgVolume"] == 500_000

    def test_market_cap_is_none(self):
        hist = self._make_hist()
        q = _derive_quote("AAPL", hist)
        assert q["marketCap"] is None

    def test_empty_hist_returns_empty_dict(self):
        q = _derive_quote("AAPL", [])
        assert q == {}
