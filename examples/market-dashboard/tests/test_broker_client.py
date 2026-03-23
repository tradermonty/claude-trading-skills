# tests/test_broker_client.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from unittest.mock import MagicMock


def test_alpaca_client_satisfies_protocol():
    """AlpacaClient must satisfy BrokerClient Protocol at runtime."""
    from broker_client import BrokerClient
    from alpaca_client import AlpacaClient

    # isinstance check works for runtime_checkable Protocol
    client = AlpacaClient(api_key="k", secret_key="s", paper=True)
    assert isinstance(client, BrokerClient)


def test_broker_client_protocol_has_required_methods():
    """BrokerClient Protocol exposes all required methods."""
    from broker_client import BrokerClient
    import inspect

    required = {
        "get_account",
        "get_positions",
        "get_last_price",
        "get_current_volume",
        "place_bracket_order",
        "place_market_sell",
        "replace_order_stop",
        "subscribe_bars",
        "is_configured",
    }
    members = set(dir(BrokerClient))
    missing = required - members
    assert not missing, f"Missing from BrokerClient: {missing}"
