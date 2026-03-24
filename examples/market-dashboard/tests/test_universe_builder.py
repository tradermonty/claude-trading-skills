# tests/test_universe_builder.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import json
import tempfile
from unittest.mock import MagicMock, patch


def _make_mock_ibkr():
    """Build an IBKRClient mock that returns plausible data."""
    mock = MagicMock()
    mock.is_configured = True

    # reqContractDetails returns a list of stock contracts
    mock_detail1 = MagicMock()
    mock_detail1.contract.symbol = "EQNR"
    mock_detail1.longName = "Equinor ASA"

    mock_detail2 = MagicMock()
    mock_detail2.contract.symbol = "DNB"
    mock_detail2.longName = "DNB Bank ASA"

    mock.reqContractDetails.return_value = [mock_detail1, mock_detail2]

    # reqHistoricalData returns OHLCV bars
    def _make_bars(symbol):
        bars = []
        for i in range(60):
            bar = MagicMock()
            bar.open = 100.0 + i
            bar.high = 105.0 + i
            bar.low = 99.0 + i
            bar.close = 102.0 + i
            bar.volume = 500_000
            bars.append(bar)
        return bars

    mock._ib = MagicMock()
    mock._ib.reqHistoricalData.side_effect = lambda *a, **kw: _make_bars("X")
    return mock


def test_build_universe_creates_cache_file():
    """build_universe writes cache/<market-id>-universe.json."""
    from universe_builder import UniverseBuilder

    mock_ibkr = _make_mock_ibkr()
    cache_dir = Path(tempfile.mkdtemp())
    market_config = {
        "id": "oslo",
        "exchange": "OSE",
        "currency": "NOK",
        "tz": "Europe/Oslo",
        "min_market_cap": 1_000_000_000,
        "min_avg_volume": 100_000,
    }

    builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir, request_delay=0)
    builder.build_universe(market_config)

    output_file = cache_dir / "oslo-universe.json"
    assert output_file.exists()


def test_build_universe_output_format():
    """Output JSON has market, updated, symbols fields."""
    from universe_builder import UniverseBuilder

    mock_ibkr = _make_mock_ibkr()
    cache_dir = Path(tempfile.mkdtemp())
    market_config = {
        "id": "oslo",
        "exchange": "OSE",
        "currency": "NOK",
        "tz": "Europe/Oslo",
        "min_market_cap": 0,        # no filter — include all
        "min_avg_volume": 0,
    }

    builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir, request_delay=0)
    builder.build_universe(market_config)

    data = json.loads((cache_dir / "oslo-universe.json").read_text())
    assert data["market"] == "oslo"
    assert "updated" in data
    assert "symbols" in data
    assert isinstance(data["symbols"], list)


def test_build_universe_filters_by_volume():
    """Symbols below min_avg_volume threshold are excluded."""
    from universe_builder import UniverseBuilder

    mock_ibkr = _make_mock_ibkr()
    # Override bars to return low volume
    def _low_vol_bars(*a, **kw):
        bar = MagicMock()
        bar.close = 100.0
        bar.volume = 10_000  # below threshold
        return [bar] * 60

    mock_ibkr._ib.reqHistoricalData.side_effect = _low_vol_bars

    cache_dir = Path(tempfile.mkdtemp())
    market_config = {
        "id": "oslo",
        "exchange": "OSE",
        "currency": "NOK",
        "tz": "Europe/Oslo",
        "min_market_cap": 0,
        "min_avg_volume": 100_000,  # require 100k avg volume
    }

    builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir, request_delay=0)
    builder.build_universe(market_config)

    data = json.loads((cache_dir / "oslo-universe.json").read_text())
    assert data["symbols"] == []


def test_build_universe_skips_when_ibkr_not_configured():
    """build_universe returns empty result when IBKR not connected."""
    from universe_builder import UniverseBuilder

    mock_ibkr = MagicMock()
    mock_ibkr.is_configured = False

    cache_dir = Path(tempfile.mkdtemp())
    market_config = {"id": "oslo", "exchange": "OSE", "currency": "NOK"}

    builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir, request_delay=0)
    result = builder.build_universe(market_config)
    assert result == []


def test_request_delay_is_respected(monkeypatch):
    """build_universe sleeps request_delay seconds between symbol requests."""
    from universe_builder import UniverseBuilder
    import time

    mock_ibkr = _make_mock_ibkr()
    cache_dir = Path(tempfile.mkdtemp())
    market_config = {
        "id": "oslo",
        "exchange": "OSE",
        "currency": "NOK",
        "min_market_cap": 0,
        "min_avg_volume": 0,
    }

    sleep_calls = []
    monkeypatch.setattr("universe_builder.time.sleep", lambda s: sleep_calls.append(s))

    builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir, request_delay=6)
    builder.build_universe(market_config)

    # Should have slept once per symbol fetched
    assert all(s == 6 for s in sleep_calls)
    assert len(sleep_calls) >= 1


def test_build_queue_writes_queue_file():
    """build_queue writes cache/universe-queue.json."""
    from universe_builder import UniverseBuilder
    mock_ibkr = MagicMock()
    mock_ibkr.is_configured = False
    cache_dir = Path(tempfile.mkdtemp())

    mock_stocks = [
        {"Ticker": "AAPL", "Price": "175.0", "Volume": "80000000"},
        {"Ticker": "MSFT", "Price": "420.0", "Volume": "30000000"},
    ]

    with patch("universe_builder.Overview") as mock_overview, \
         patch("universe_builder.requests.get") as mock_get:
        mock_overview.return_value.screener_view.return_value = mock_stocks
        mock_get.return_value.json.return_value = {"companyNewsScore": 0.6}
        mock_get.return_value.status_code = 200

        builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir)
        builder.build_queue(finnhub_api_key="test_key")

    assert (cache_dir / "universe-queue.json").exists()


def test_build_queue_output_format():
    """universe-queue.json has candidates list with symbol and sentiment_score."""
    from universe_builder import UniverseBuilder
    mock_ibkr = MagicMock()
    mock_ibkr.is_configured = False
    cache_dir = Path(tempfile.mkdtemp())

    mock_stocks = [{"Ticker": "AAPL", "Price": "175.0", "Volume": "80000000"}]

    with patch("universe_builder.Overview") as mock_overview, \
         patch("universe_builder.requests.get") as mock_get:
        mock_overview.return_value.screener_view.return_value = mock_stocks
        mock_get.return_value.json.return_value = {"companyNewsScore": 0.75}
        mock_get.return_value.status_code = 200

        builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir)
        builder.build_queue(finnhub_api_key="test_key")

    data = json.loads((cache_dir / "universe-queue.json").read_text())
    assert "candidates" in data
    assert "updated" in data
    assert data["candidates"][0]["symbol"] == "AAPL"
    assert "sentiment_score" in data["candidates"][0]
    assert "scanned_count" in data
    assert data["scanned_count"] == 0


def test_build_queue_sorts_by_sentiment():
    """Candidates are sorted highest sentiment first."""
    from universe_builder import UniverseBuilder
    mock_ibkr = MagicMock()
    mock_ibkr.is_configured = False
    cache_dir = Path(tempfile.mkdtemp())

    mock_stocks = [
        {"Ticker": "AAPL", "Price": "175.0", "Volume": "80000000"},
        {"Ticker": "MSFT", "Price": "420.0", "Volume": "30000000"},
    ]

    sentiment_map = {"AAPL": 0.3, "MSFT": 0.9}

    def mock_get(url, *a, **kw):
        symbol = url.split("symbol=")[1].split("&")[0]
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"companyNewsScore": sentiment_map.get(symbol, 0.5)}
        return resp

    with patch("universe_builder.Overview") as mock_overview, \
         patch("universe_builder.requests.get", side_effect=mock_get):
        mock_overview.return_value.screener_view.return_value = mock_stocks
        builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir)
        builder.build_queue(finnhub_api_key="test_key")

    data = json.loads((cache_dir / "universe-queue.json").read_text())
    assert data["candidates"][0]["symbol"] == "MSFT"


def test_build_queue_works_without_finnhub_key():
    """build_queue skips Finnhub scoring when no key provided, uses 0.5 default."""
    from universe_builder import UniverseBuilder
    mock_ibkr = MagicMock()
    mock_ibkr.is_configured = False
    cache_dir = Path(tempfile.mkdtemp())

    mock_stocks = [{"Ticker": "AAPL", "Price": "175.0", "Volume": "80000000"}]

    with patch("universe_builder.Overview") as mock_overview:
        mock_overview.return_value.screener_view.return_value = mock_stocks
        builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir)
        builder.build_queue(finnhub_api_key="")

    data = json.loads((cache_dir / "universe-queue.json").read_text())
    assert data["candidates"][0]["sentiment_score"] == 0.5


def test_build_queue_returns_empty_when_finviz_fails():
    """build_queue returns [] and does not raise when FINVIZ screener_view throws."""
    from universe_builder import UniverseBuilder
    mock_ibkr = MagicMock()
    mock_ibkr.is_configured = False
    cache_dir = Path(tempfile.mkdtemp())

    with patch("universe_builder.Overview") as mock_overview:
        mock_overview.return_value.screener_view.side_effect = Exception("network error")
        builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir)
        result = builder.build_queue(finnhub_api_key="")

    assert result == []
    assert not (cache_dir / "universe-queue.json").exists()


def _make_fmp_client_mock(price=150.0, avg_vol=1_000_000):
    mock = MagicMock()
    quote = {"price": price, "avgVolume": avg_vol}
    mock.get_batch_quotes.return_value = {"AAPL": quote, "MSFT": quote}
    # Newest-first bars: bars[0] is most recent (price), bars[-1] is oldest (lower)
    # So price > MA50 > MA200 — uptrending
    bars = [{"close": price - i * 0.1, "volume": avg_vol} for i in range(260)]
    mock.get_batch_historical.return_value = {"AAPL": bars, "MSFT": bars}
    return mock


def _make_falling_fmp_mock(price=50.0, avg_vol=1_000_000):
    mock = MagicMock()
    quote = {"price": price, "avgVolume": avg_vol}
    mock.get_batch_quotes.return_value = {"AAPL": quote, "MSFT": quote}
    # Newest-first bars: bars[0] is most recent (50), older bars are much higher
    # So price (50) < MA50 (~50 + rising) — failing criteria
    bars = [{"close": price + i * 0.5, "volume": avg_vol} for i in range(260)]
    mock.get_batch_historical.return_value = {"AAPL": bars, "MSFT": bars}
    return mock


def test_run_nightly_batch_writes_universe_file():
    """run_nightly_batch writes cache/vcp-universe.json."""
    from universe_builder import UniverseBuilder
    mock_ibkr = MagicMock()
    mock_ibkr.is_configured = False
    cache_dir = Path(tempfile.mkdtemp())

    queue = {
        "updated": "2026-03-23T18:00:00Z",
        "scanned_count": 0,
        "candidates": [
            {"symbol": "AAPL", "sentiment_score": 0.8, "status": "pending"},
        ]
    }
    (cache_dir / "universe-queue.json").write_text(json.dumps(queue))

    with patch("universe_builder.FMPClient", return_value=_make_fmp_client_mock()):
        builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir)
        builder.run_nightly_batch(fmp_api_key="test_key", batch_size=20)

    assert (cache_dir / "vcp-universe.json").exists()


def test_run_nightly_batch_adds_passing_stocks():
    """Stocks passing FMP criteria are added to vcp-universe.json as active."""
    from universe_builder import UniverseBuilder
    mock_ibkr = MagicMock()
    mock_ibkr.is_configured = False
    cache_dir = Path(tempfile.mkdtemp())

    queue = {
        "updated": "2026-03-23T18:00:00Z",
        "scanned_count": 0,
        "candidates": [
            {"symbol": "AAPL", "sentiment_score": 0.8, "status": "pending"},
        ]
    }
    (cache_dir / "universe-queue.json").write_text(json.dumps(queue))

    with patch("universe_builder.FMPClient", return_value=_make_fmp_client_mock(price=150.0)):
        builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir)
        builder.run_nightly_batch(fmp_api_key="test_key", batch_size=20)

    data = json.loads((cache_dir / "vcp-universe.json").read_text())
    symbols = [s["symbol"] for s in data["symbols"]]
    assert "AAPL" in symbols
    assert data["symbols"][0]["status"] == "active"


def test_run_nightly_batch_weakening_to_removed():
    """A weakening stock that fails again is removed from universe."""
    from universe_builder import UniverseBuilder
    mock_ibkr = MagicMock()
    mock_ibkr.is_configured = False
    cache_dir = Path(tempfile.mkdtemp())

    universe = {
        "updated": "2026-03-23T18:00:00Z",
        "symbols": [
            {"symbol": "AAPL", "status": "weakening", "sentiment_score": 0.8}
        ]
    }
    (cache_dir / "vcp-universe.json").write_text(json.dumps(universe))
    (cache_dir / "universe-queue.json").write_text(json.dumps({
        "updated": "2026-03-23T18:00:00Z", "scanned_count": 0, "candidates": []
    }))

    with patch("universe_builder.FMPClient", return_value=_make_falling_fmp_mock()):
        builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir)
        builder.run_nightly_batch(fmp_api_key="test_key", batch_size=20)

    data = json.loads((cache_dir / "vcp-universe.json").read_text())
    symbols = [s["symbol"] for s in data["symbols"]]
    assert "AAPL" not in symbols


def test_run_nightly_batch_active_to_weakening():
    """An active stock that fails criteria becomes weakening (not removed immediately)."""
    from universe_builder import UniverseBuilder
    mock_ibkr = MagicMock()
    mock_ibkr.is_configured = False
    cache_dir = Path(tempfile.mkdtemp())

    universe = {
        "updated": "2026-03-23T18:00:00Z",
        "symbols": [
            {"symbol": "AAPL", "status": "active", "sentiment_score": 0.8}
        ]
    }
    (cache_dir / "vcp-universe.json").write_text(json.dumps(universe))
    (cache_dir / "universe-queue.json").write_text(json.dumps({
        "updated": "2026-03-23T18:00:00Z", "scanned_count": 0, "candidates": []
    }))

    # Falling mock — AAPL price below MA50
    falling_mock = _make_falling_fmp_mock()

    with patch("universe_builder.FMPClient", return_value=falling_mock):
        builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir)
        builder.run_nightly_batch(fmp_api_key="test_key", batch_size=20)

    data = json.loads((cache_dir / "vcp-universe.json").read_text())
    aapl = next((s for s in data["symbols"] if s["symbol"] == "AAPL"), None)
    assert aapl is not None
    assert aapl["status"] == "weakening"


def test_run_nightly_batch_weakening_to_active_recovery():
    """A weakening stock that passes criteria again is restored to active."""
    from universe_builder import UniverseBuilder
    mock_ibkr = MagicMock()
    mock_ibkr.is_configured = False
    cache_dir = Path(tempfile.mkdtemp())

    universe = {
        "updated": "2026-03-23T18:00:00Z",
        "symbols": [
            {"symbol": "AAPL", "status": "weakening", "sentiment_score": 0.8}
        ]
    }
    (cache_dir / "vcp-universe.json").write_text(json.dumps(universe))
    (cache_dir / "universe-queue.json").write_text(json.dumps({
        "updated": "2026-03-23T18:00:00Z", "scanned_count": 0, "candidates": []
    }))

    with patch("universe_builder.FMPClient", return_value=_make_fmp_client_mock(price=150.0)):
        builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir)
        builder.run_nightly_batch(fmp_api_key="test_key", batch_size=20)

    data = json.loads((cache_dir / "vcp-universe.json").read_text())
    aapl = next((s for s in data["symbols"] if s["symbol"] == "AAPL"), None)
    assert aapl is not None
    assert aapl["status"] == "active"


def test_run_nightly_batch_adds_passing_stocks_by_symbol():
    """Passing stock added as active — check by symbol not index."""
    from universe_builder import UniverseBuilder
    mock_ibkr = MagicMock()
    mock_ibkr.is_configured = False
    cache_dir = Path(tempfile.mkdtemp())

    queue = {
        "updated": "2026-03-23T18:00:00Z",
        "scanned_count": 0,
        "candidates": [
            {"symbol": "AAPL", "sentiment_score": 0.8, "status": "pending"},
        ]
    }
    (cache_dir / "universe-queue.json").write_text(json.dumps(queue))

    with patch("universe_builder.FMPClient", return_value=_make_fmp_client_mock(price=150.0)):
        builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir)
        builder.run_nightly_batch(fmp_api_key="test_key", batch_size=20)

    data = json.loads((cache_dir / "vcp-universe.json").read_text())
    aapl = next((s for s in data["symbols"] if s["symbol"] == "AAPL"), None)
    assert aapl is not None
    assert aapl["status"] == "active"
