"""FINVIZ Elite export request contract (#799).

FINVIZ moves the screener CSV export to ``/export/screener`` and requires
``type=stocks|etf`` from 2026-12-07. These tests pin the request so the
screening conditions stay byte-identical across the migration, and check
that the CSV parser is independent of column order and a UTF-8 BOM.
"""

from unittest.mock import MagicMock

import pytest
import requests
from screen_dividend_stocks import FINVIZClient

EXPECTED_FILTERS = (
    "cap_midover,fa_div_o3,fa_divgrowth_3yo5,fa_eps3years_pos,"
    "fa_pb_u2,fa_pe_u20,fa_sales3years_pos,geo_usa"
)
SECRET = "sk-test-not-a-real-key-799"  # pragma: allowlist secret

# Today's v=151 export (saved custom columns), the pinned/new-screener shape,
# and a reordered variant. All must yield the same tickers.
CSV_LEGACY_18 = (
    "No.,Ticker,Company,Industry,Market Cap,EPS Growth This Year,"
    "EPS Growth Next Year,Sales Growth Past 5 Years,"
    "Sales Growth Quarter Over Quarter,EPS Growth Quarter Over Quarter,"
    "EPS Surprise,Revenue Surprise,Performance (Week),Performance (YTD),"
    "Earnings Date,Relative Volume,Change,After-Hours Change\n"
    '1,AAA,A Co,Banks,765.59,1%,2%,3%,4%,5%,6%,7%,8%,9%,"Nov 1",1.1,0.5%,0.1%\n'
    '2,BBB,B Co,Banks,1200.00,1%,2%,3%,4%,5%,6%,7%,8%,9%,"Nov 2",0.9,-0.5%,0.0%\n'
)
CSV_NEW_SCREENER = "No.,Ticker,Market Cap,Change\n1,AAA,765.59,0.5%\n2,BBB,1200.00,-0.5%\n"
CSV_REORDERED = "Change,Market Cap,Ticker\n0.5%,765.59,AAA\n-0.5%,1200.00,BBB\n"


def _resp(status=200, body=""):
    resp = MagicMock()
    resp.status_code = status
    resp.content = body.encode("utf-8") if isinstance(body, str) else body
    resp.text = body if isinstance(body, str) else body.decode("utf-8")
    return resp


def _client(response):
    client = FINVIZClient(SECRET)
    client.session = MagicMock()
    client.session.get.return_value = response
    return client


def test_request_targets_new_export_endpoint_with_type_stocks():
    client = _client(_resp(200, CSV_NEW_SCREENER))
    client.screen_stocks()
    args, kwargs = client.session.get.call_args
    assert args[0] == "https://elite.finviz.com/export/screener"
    params = kwargs["params"]
    assert params["type"] == "stocks"
    assert params["v"] == "151"
    assert params["ft"] == "4"
    assert params["f"] == EXPECTED_FILTERS
    assert params["auth"] == SECRET


def test_no_legacy_export_ashx_reference():
    assert "export.ashx" not in FINVIZClient.BASE_URL


@pytest.mark.parametrize(
    "body",
    [CSV_LEGACY_18, CSV_NEW_SCREENER, CSV_REORDERED, "﻿" + CSV_NEW_SCREENER],
    ids=["legacy-18-cols", "new-screener", "reordered", "utf8-bom"],
)
def test_ticker_set_is_independent_of_column_layout(body):
    assert _client(_resp(200, body)).screen_stocks() == {"AAA", "BBB"}


@pytest.mark.parametrize("status", [200, 403, 500])
def test_api_key_never_printed(status, capsys):
    _client(_resp(status, CSV_NEW_SCREENER if status == 200 else "")).screen_stocks()
    captured = capsys.readouterr()
    assert SECRET not in captured.out
    assert SECRET not in captured.err


def test_api_key_never_printed_on_request_exception(capsys):
    client = FINVIZClient(SECRET)
    client.session = MagicMock()
    client.session.get.side_effect = requests.exceptions.ConnectionError(
        f"failed: https://elite.finviz.com/export/screener?auth={SECRET}"
    )
    assert client.screen_stocks() == set()
    captured = capsys.readouterr()
    assert SECRET not in captured.out
    assert SECRET not in captured.err
