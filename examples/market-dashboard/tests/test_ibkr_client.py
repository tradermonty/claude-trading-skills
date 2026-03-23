# tests/test_ibkr_client.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio


def _make_client(connected: bool = True):
    """Build IBKRClient with a mocked ib_insync IB instance."""
    from ibkr_client import IBKRClient

    mock_ib = MagicMock()
    mock_ib.isConnected.return_value = connected
    # Simulate successful connect (no exception)
    mock_ib.connect = MagicMock()

    client = IBKRClient(paper=True, _ib=mock_ib)
    return client, mock_ib


def test_is_configured_true_when_connected():
    client, mock_ib = _make_client(connected=True)
    assert client.is_configured is True


def test_is_configured_false_when_not_connected():
    client, mock_ib = _make_client(connected=False)
    assert client.is_configured is False


def test_get_account_returns_portfolio_value():
    client, mock_ib = _make_client()

    mock_account_value = MagicMock()
    mock_account_value.tag = "NetLiquidation"
    mock_account_value.value = "125000.50"
    mock_account_value.currency = "USD"

    mock_ib.accountValues.return_value = [mock_account_value]

    result = client.get_account()
    assert "portfolio_value" in result
    assert result["portfolio_value"] == pytest.approx(125000.50)


def test_get_positions_returns_list():
    client, mock_ib = _make_client()

    mock_contract = MagicMock()
    mock_contract.symbol = "EQNR"

    mock_pos = MagicMock()
    mock_pos.contract = mock_contract
    mock_pos.position = 100.0
    mock_pos.avgCost = 300.0

    mock_ib.positions.return_value = [mock_pos]

    result = client.get_positions()
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["symbol"] == "EQNR"
    assert result[0]["qty"] == 100.0


def test_get_last_price_returns_float():
    client, mock_ib = _make_client()

    mock_ticker = MagicMock()
    mock_ticker.last = 312.50

    mock_ib.reqMktData.return_value = mock_ticker
    mock_ib.sleep = MagicMock()

    result = client.get_last_price("EQNR")
    assert result == pytest.approx(312.50)


def test_place_bracket_order_returns_id_and_stop_order_id():
    client, mock_ib = _make_client()

    mock_parent = MagicMock()
    mock_parent.orderId = 101

    mock_tp = MagicMock()
    mock_tp.orderId = 102

    mock_stop = MagicMock()
    mock_stop.orderId = 103

    mock_trade = MagicMock()
    mock_trade.order.orderId = 101

    mock_ib.placeOrder.side_effect = [mock_trade, MagicMock(), MagicMock()]
    mock_ib.client.getReqId.side_effect = [101, 102, 103]

    # Mock bracket order construction
    with patch("ibkr_client.LimitOrder") as mock_limit, \
         patch("ibkr_client.StopOrder") as mock_stop_order, \
         patch("ibkr_client.LimitOrder") as mock_tp_order:
        mock_limit.return_value = mock_parent
        result = client.place_bracket_order(
            symbol="EQNR",
            qty=10,
            limit_price=310.0,
            stop_price=300.0,
            take_profit_price=330.0,
        )

    assert "id" in result
    assert "stop_order_id" in result


def test_ibkr_satisfies_broker_client_protocol():
    """IBKRClient satisfies BrokerClient Protocol."""
    from broker_client import BrokerClient
    client, _ = _make_client()
    assert isinstance(client, BrokerClient)


def test_subscribe_bars_creates_realtime_bars():
    """subscribe_bars calls reqRealTimeBars for each symbol."""
    client, mock_ib = _make_client()

    callback = AsyncMock()

    async def run():
        # subscribe_bars should register bars and then wait; we just check it doesn't raise
        # and that reqRealTimeBars is called for each symbol
        task = asyncio.create_task(
            client.subscribe_bars(["EQNR", "SHEL"], callback)
        )
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
    assert mock_ib.reqRealTimeBars.call_count == 2
