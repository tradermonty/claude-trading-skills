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
