"""Tests for broker_short_inventory_adapter + alpaca_inventory_adapter."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure adapters/ is on sys.path so `from alpaca_inventory_adapter` works.
ADAPTERS_DIR = Path(__file__).resolve().parents[1] / "adapters"
if str(ADAPTERS_DIR) not in sys.path:
    sys.path.insert(0, str(ADAPTERS_DIR))

from broker_short_inventory_adapter import (
    BrokerNotConfiguredError,
    ManualBrokerAdapter,
)


def _alpaca_response(*, shortable: bool, easy_to_borrow: bool) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "id": "asset-id",
        "class": "us_equity",
        "exchange": "NASDAQ",
        "symbol": "XYZ",
        "tradable": True,
        "shortable": shortable,
        "easy_to_borrow": easy_to_borrow,
    }
    resp.raise_for_status = MagicMock()
    return resp


def _make_alpaca():
    """Avoid importing the module at file scope so the patch below doesn't
    need to be active during collection."""
    from alpaca_inventory_adapter import AlpacaInventoryAdapter

    return AlpacaInventoryAdapter(
        api_key="key",  # pragma: allowlist secret
        secret_key="secret",  # pragma: allowlist secret
        paper=True,
    )


class TestManualAdapter:
    def test_manual_blocks_by_default(self):
        adapter = ManualBrokerAdapter()
        status = adapter.get_inventory_status("XYZ")
        assert status["can_open_new_short"] is False
        assert status["borrow_fee_manual_check_required"] is True
        assert status["manual_locate_required"] is True
        assert status["source"] == "manual"


class TestAlpacaAdapterETB:
    def test_etb_can_open_new_short(self):
        with patch(
            "requests.get", return_value=_alpaca_response(shortable=True, easy_to_borrow=True)
        ):
            adapter = _make_alpaca()
            status = adapter.get_inventory_status("XYZ")
        assert status["can_open_new_short"] is True
        assert status["shortable"] is True
        assert status["easy_to_borrow"] is True
        assert status["borrow_fee_apr"] == 0.0
        assert status["borrow_fee_manual_check_required"] is False
        assert status["manual_locate_required"] is True
        assert status["source"] == "alpaca_v2_assets"


class TestAlpacaAdapterHTB:
    def test_htb_cannot_open(self):
        with patch(
            "requests.get", return_value=_alpaca_response(shortable=True, easy_to_borrow=False)
        ):
            adapter = _make_alpaca()
            status = adapter.get_inventory_status("HTB")
        assert status["can_open_new_short"] is False
        assert status["borrow_fee_apr"] is None
        assert status["borrow_fee_manual_check_required"] is True

    def test_not_shortable_cannot_open(self):
        with patch(
            "requests.get", return_value=_alpaca_response(shortable=False, easy_to_borrow=False)
        ):
            adapter = _make_alpaca()
            status = adapter.get_inventory_status("LOCK")
        assert status["can_open_new_short"] is False
        assert status["shortable"] is False


class TestAlpacaAdapterErrors:
    def test_missing_credentials_raises(self, monkeypatch):
        from alpaca_inventory_adapter import AlpacaInventoryAdapter

        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
        with pytest.raises(BrokerNotConfiguredError):
            AlpacaInventoryAdapter()

    def test_http_error_propagates(self):
        bad = MagicMock()
        bad.raise_for_status.side_effect = RuntimeError("HTTP 500")
        with patch("requests.get", return_value=bad):
            adapter = _make_alpaca()
            with pytest.raises(RuntimeError):
                adapter.get_inventory_status("XYZ")


class TestManualLocateAlwaysTrue:
    def test_etb_still_requires_manual_locate(self):
        with patch(
            "requests.get", return_value=_alpaca_response(shortable=True, easy_to_borrow=True)
        ):
            adapter = _make_alpaca()
            status = adapter.get_inventory_status("XYZ")
        # Even on ETB names, the trader must confirm locate at the broker.
        # This is the contractual safety net.
        assert status["manual_locate_required"] is True
