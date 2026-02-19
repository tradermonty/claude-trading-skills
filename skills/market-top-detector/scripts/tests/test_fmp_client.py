"""Tests for FMP Client VIX term structure auto-detection"""

from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestVixTermStructure:
    """Test VIX term structure auto-classification."""

    def _make_client(self):
        """Create a mock FMPClient without real API key."""
        with patch.dict(os.environ, {"FMP_API_KEY": "test_key"}):
            from fmp_client import FMPClient
            client = FMPClient(api_key="test_key")
        return client

    def test_steep_contango(self):
        """VIX/VIX3M < 0.85 -> steep_contango."""
        client = self._make_client()
        client.get_quote = MagicMock(side_effect=lambda s:
            [{"price": 12.0}] if "VIX3M" not in s else [{"price": 16.0}])
        result = client.get_vix_term_structure()
        assert result is not None
        assert result["classification"] == "steep_contango"
        assert result["ratio"] < 0.85

    def test_contango(self):
        """VIX/VIX3M 0.85-0.95 -> contango."""
        client = self._make_client()
        client.get_quote = MagicMock(side_effect=lambda s:
            [{"price": 14.0}] if "VIX3M" not in s else [{"price": 15.5}])
        result = client.get_vix_term_structure()
        assert result["classification"] == "contango"

    def test_flat(self):
        """VIX/VIX3M 0.95-1.05 -> flat."""
        client = self._make_client()
        client.get_quote = MagicMock(side_effect=lambda s:
            [{"price": 15.0}] if "VIX3M" not in s else [{"price": 15.2}])
        result = client.get_vix_term_structure()
        assert result["classification"] == "flat"

    def test_backwardation(self):
        """VIX/VIX3M > 1.05 -> backwardation."""
        client = self._make_client()
        client.get_quote = MagicMock(side_effect=lambda s:
            [{"price": 22.0}] if "VIX3M" not in s else [{"price": 18.0}])
        result = client.get_vix_term_structure()
        assert result["classification"] == "backwardation"

    def test_unavailable(self):
        """VIX3M unavailable -> None."""
        client = self._make_client()
        client.get_quote = MagicMock(side_effect=lambda s:
            [{"price": 15.0}] if "VIX3M" not in s else None)
        result = client.get_vix_term_structure()
        assert result is None
