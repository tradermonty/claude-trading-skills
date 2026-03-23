# tests/test_alpaca_client.py
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _mock_trading_client():
    m = MagicMock()
    acct = MagicMock()
    acct.portfolio_value = "100000.00"
    acct.buying_power = "50000.00"
    acct.cash = "50000.00"
    m.get_account.return_value = acct
    m.get_all_positions.return_value = []
    return m


def _mock_data_client(price=150.25):
    m = MagicMock()
    trade = MagicMock()
    trade.price = price
    m.get_stock_latest_trade.return_value = {"AAPL": trade}
    return m


def test_get_account_returns_floats():
    from alpaca_client import AlpacaClient
    client = AlpacaClient(api_key="k", secret_key="s", _trading_client=_mock_trading_client())
    acct = client.get_account()
    assert acct["portfolio_value"] == 100000.0
    assert acct["buying_power"] == 50000.0
    assert acct["cash"] == 50000.0


def test_get_positions_empty():
    from alpaca_client import AlpacaClient
    client = AlpacaClient(api_key="k", secret_key="s", _trading_client=_mock_trading_client())
    assert client.get_positions() == []


def test_get_positions_with_data():
    from alpaca_client import AlpacaClient
    mock_tc = _mock_trading_client()
    pos = MagicMock()
    pos.symbol = "AAPL"
    pos.qty = "10"
    pos.market_value = "1502.50"
    pos.unrealized_pl = "52.50"
    pos.unrealized_plpc = "0.0362"
    pos.avg_entry_price = "145.00"
    pos.current_price = "150.25"
    mock_tc.get_all_positions.return_value = [pos]
    client = AlpacaClient(api_key="k", secret_key="s", _trading_client=mock_tc)
    positions = client.get_positions()
    assert len(positions) == 1
    assert positions[0]["symbol"] == "AAPL"
    assert positions[0]["qty"] == 10.0
    assert positions[0]["unrealized_pl"] == 52.50


def test_get_last_price():
    from alpaca_client import AlpacaClient
    client = AlpacaClient(api_key="k", secret_key="s", _data_client=_mock_data_client(150.25))
    assert client.get_last_price("AAPL") == 150.25


def test_place_bracket_order():
    from alpaca_client import AlpacaClient
    from alpaca.trading.requests import LimitOrderRequest
    mock_tc = _mock_trading_client()
    order = MagicMock()
    order.id = "order-123"
    order.symbol = "AAPL"
    order.qty = "10"
    order.limit_price = "150.25"
    order.status = "accepted"
    mock_tc.submit_order.return_value = order
    client = AlpacaClient(api_key="k", secret_key="s", _trading_client=mock_tc)
    result = client.place_bracket_order(symbol="AAPL", qty=10, limit_price=150.25, stop_price=145.00)
    assert result["id"] == "order-123"
    assert result["symbol"] == "AAPL"
    mock_tc.submit_order.assert_called_once()
    # Verify bracket order includes both stop_loss and take_profit (Alpaca requires both)
    submitted: LimitOrderRequest = mock_tc.submit_order.call_args[0][0]
    assert submitted.stop_loss is not None
    assert submitted.take_profit is not None


def test_is_configured_false_when_keys_empty():
    from alpaca_client import AlpacaClient
    client = AlpacaClient(api_key="", secret_key="")
    assert not client.is_configured


def test_is_configured_true_when_keys_present():
    from alpaca_client import AlpacaClient
    client = AlpacaClient(api_key="key", secret_key="secret")
    assert client.is_configured


def test_start_trading_stream_calls_stream_run():
    """start_trading_stream connects the TradingStream and runs it."""
    import asyncio
    from unittest.mock import MagicMock, patch
    from alpaca_client import AlpacaClient

    mock_stream = MagicMock()
    mock_stream.run = MagicMock()
    mock_stream.subscribe_trade_updates = lambda fn: fn  # decorator no-op

    with patch("alpaca.trading.stream.TradingStream", return_value=mock_stream):
        client = AlpacaClient(api_key="k", secret_key="s")
        asyncio.run(client.start_trading_stream())

    mock_stream.run.assert_called_once()


def make_client(trading_client=None):
    from alpaca_client import AlpacaClient
    return AlpacaClient(
        api_key="test_key",
        secret_key="test_secret",
        paper=True,
        _trading_client=trading_client or MagicMock(),
    )


def test_replace_order_stop_calls_replace_on_trading_client():
    mock_tc = MagicMock()
    mock_result = MagicMock()
    mock_result.id = "ord-abc"
    mock_result.status = "accepted"
    mock_tc.replace_order_by_id.return_value = mock_result
    client = make_client(mock_tc)
    result = client.replace_order_stop("ord-abc", 98.50)
    mock_tc.replace_order_by_id.assert_called_once()
    assert result == {"id": "ord-abc", "status": "accepted"}


def test_replace_order_stop_passes_new_stop_price():
    mock_tc = MagicMock()
    mock_result = MagicMock()
    mock_result.id = "ord-xyz"
    mock_result.status = "pending_replace"
    mock_tc.replace_order_by_id.return_value = mock_result
    client = make_client(mock_tc)
    client.replace_order_stop("ord-xyz", 102.25)
    replace_req = mock_tc.replace_order_by_id.call_args[0][1]
    assert replace_req.stop_price == 102.25


def test_place_market_sell_calls_submit_order():
    mock_tc = MagicMock()
    mock_result = MagicMock()
    mock_result.id = "sell-ord-1"
    mock_result.status = "new"
    mock_tc.submit_order.return_value = mock_result
    client = make_client(mock_tc)
    result = client.place_market_sell("AAPL", 10)
    mock_tc.submit_order.assert_called_once()
    assert result == {"id": "sell-ord-1", "status": "new"}


def test_place_market_sell_uses_sell_side_and_day_tif():
    from alpaca.trading.enums import OrderSide, TimeInForce
    mock_tc = MagicMock()
    mock_result = MagicMock()
    mock_result.id = "sell-ord-2"
    mock_result.status = "new"
    mock_tc.submit_order.return_value = mock_result
    client = make_client(mock_tc)
    client.place_market_sell("TSLA", 5)
    req = mock_tc.submit_order.call_args[0][0]
    assert req.symbol == "TSLA"
    assert req.qty == 5
    assert req.side == OrderSide.SELL
    assert req.time_in_force == TimeInForce.DAY


def _make_client():
    from alpaca_client import AlpacaClient
    return AlpacaClient(api_key="test_key", secret_key="test_secret", paper=True)


def test_place_bracket_order_returns_stop_order_id():
    """place_bracket_order must return stop_order_id from the bracket order response."""
    import pytest
    client = _make_client()

    # Build a mock bracket order response with legs
    stop_leg = MagicMock()
    stop_leg.id = "stop-leg-id-123"
    stop_leg.stop_price = 145.0  # has stop_price → identified as stop leg

    tp_leg = MagicMock()
    tp_leg.id = "tp-leg-id-456"
    tp_leg.stop_price = None  # no stop_price → take-profit leg

    mock_order = MagicMock()
    mock_order.id = "parent-order-id-789"
    mock_order.symbol = "AAPL"
    mock_order.qty = 10
    mock_order.limit_price = 150.0
    mock_order.status = "accepted"
    # Alpaca bracket orders have legs: [take_profit_leg, stop_loss_leg]
    mock_order.legs = [tp_leg, stop_leg]

    mock_trading = MagicMock()
    mock_trading.submit_order.return_value = mock_order
    client._trading_client = mock_trading

    result = client.place_bracket_order(
        symbol="AAPL", qty=10, limit_price=150.0, stop_price=145.0
    )

    assert "id" in result
    assert "stop_order_id" in result
    assert result["id"] == "parent-order-id-789"
    assert result["stop_order_id"] == "stop-leg-id-123"


def test_alpaca_satisfies_broker_client_protocol():
    """AlpacaClient satisfies BrokerClient after subscribe_bars is added."""
    from broker_client import BrokerClient
    client = _make_client()
    assert isinstance(client, BrokerClient)


def test_subscribe_bars_calls_stream_subscribe_and_run():
    """subscribe_bars wraps StockDataStream correctly."""
    import asyncio
    from unittest.mock import patch
    client = _make_client()

    mock_stream = MagicMock()
    mock_stream.subscribe_bars = MagicMock()
    mock_stream.run = MagicMock()

    callback = MagicMock()

    async def run():
        with patch("alpaca_client.StockDataStream", return_value=mock_stream):
            await client.subscribe_bars(["AAPL", "MSFT"], callback)

    asyncio.run(run())

    mock_stream.subscribe_bars.assert_called_once()
    mock_stream.run.assert_called_once()
