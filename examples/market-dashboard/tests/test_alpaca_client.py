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
