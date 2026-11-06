"""FMP /stable migration: sector screener uses /stable/company-screener.

fetch_sector_stocks() used v3 /stock-screener (403 for keys issued after
2025-08-31). It now uses the generated stable-only Session transport; extraction is unchanged.
"""

from unittest.mock import MagicMock, patch

import find_pairs  # noqa: E402
import statsmodels  # noqa: F401


def _resp(status_code, payload):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    return resp


@patch("requests.Session")
def test_uses_stable_company_screener_first(mock_get):
    mock_get.return_value.get.return_value = _resp(
        200,
        [
            {
                "symbol": "NVDA",
                "companyName": "NVIDIA Corporation",
                "marketCap": 5_343_290_069_887,
                "sector": "Technology",
                "exchangeShortName": "NASDAQ",
                "isActivelyTrading": True,
            }
        ],
    )
    stocks = find_pairs.fetch_sector_stocks("Technology", "key")

    assert stocks[0]["symbol"] == "NVDA"
    assert stocks[0]["name"] == "NVIDIA Corporation"
    assert stocks[0]["exchange"] == "NASDAQ"
    assert stocks[0]["marketCap"] == 5_343_290_069_887

    call = mock_get.return_value.get.call_args_list[0]
    assert call[0][0].endswith("/stable/company-screener")
    assert call[1]["params"]["sector"] == "Technology"
    assert call[1]["params"]["marketCapMoreThan"] == 2_000_000_000


@patch("requests.Session")
def test_stable_failure_does_not_attempt_legacy_screener(mock_get):
    import pytest

    mock_get.return_value.get.return_value = _resp(403, {})
    with pytest.raises(SystemExit):
        find_pairs.fetch_sector_stocks("Technology", "key")
    urls = [call[0][0] for call in mock_get.return_value.get.call_args_list]
    assert len(urls) == 1
    assert urls[0].endswith("/stable/company-screener")


@patch("requests.Session")
def test_filters_inactive_symbols(mock_get):
    mock_get.return_value.get.return_value = _resp(
        200,
        [
            {"symbol": "ACTIVE", "isActivelyTrading": True},
            {"symbol": "DELISTED", "isActivelyTrading": False},
        ],
    )
    stocks = find_pairs.fetch_sector_stocks("Technology", "key")
    assert [s["symbol"] for s in stocks] == ["ACTIVE"]
