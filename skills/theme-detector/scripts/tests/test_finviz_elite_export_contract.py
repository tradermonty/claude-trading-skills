"""FINVIZ Elite export request contract for theme-detector (#799).

From 2026-12-07 FINVIZ serves the screener CSV export from
``/export/screener`` with a required ``type=``, and saved custom columns
from the old screener stop applying. The selector reads Market Cap and
Change and Volume, so it pins ``c=1,6,66,67`` instead of
relying on saved settings. These tests pin the request and check that the
parsed rows do not depend on column order, extra columns or a UTF-8 BOM.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest
import representative_stock_selector as rss
from representative_stock_selector import (
    RepresentativeStockSelector,
    _parse_change,
    _parse_volume,
)

SECRET = "sk-test-not-a-real-key-799"  # pragma: allowlist secret
INDUSTRY = "Semiconductors"

CSV_LEGACY_18 = (
    "No.,Ticker,Company,Industry,Market Cap,EPS Growth This Year,"
    "EPS Growth Next Year,Sales Growth Past 5 Years,"
    "Sales Growth Quarter Over Quarter,EPS Growth Quarter Over Quarter,"
    "EPS Surprise,Revenue Surprise,Performance (Week),Performance (YTD),"
    "Earnings Date,Relative Volume,Change,After-Hours Change\n"
    '1,AAA,A Co,Semiconductors,765.59,1%,2%,3%,4%,5%,6%,7%,8%,9%,"Nov 1",1.1,2.50%,0.1%\n'
    '2,BBB,B Co,Semiconductors,12000.00,1%,2%,3%,4%,5%,6%,7%,8%,9%,"Nov 2",0.9,-1.25%,0.0%\n'
)
CSV_PINNED = "Ticker,Market Cap,Change\nAAA,765.59,2.50%\nBBB,12000.00,-1.25%\n"
CSV_PINNED_WITH_VOLUME = (
    "Ticker,Market Cap,Change,Volume\nAAA,765.59,2.50%,1234567\nBBB,12000.00,-1.25%,2000000\n"
)
CSV_PINNED_WITH_NO = "No.,Ticker,Market Cap,Change\n1,AAA,765.59,2.50%\n2,BBB,12000.00,-1.25%\n"
CSV_REORDERED = "Change,Ticker,Market Cap\n2.50%,AAA,765.59\n-1.25%,BBB,12000.00\n"

# Elite writes Market Cap in millions of dollars (#800), so pin dollar literals
# rather than a parser call that would follow any parser regression.
EXPECTED = [
    ("AAA", 765_590_000, _parse_change("2.50%")),
    ("BBB", 12_000_000_000, _parse_change("-1.25%")),
]


def _selector(**kwargs):
    return RepresentativeStockSelector(
        finviz_elite_key=SECRET, finviz_mode="elite", rate_limit_sec=0, **kwargs
    )


def _resp(status=200, text=""):
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.content = text.encode("utf-8")
    return resp


def _fetch(text, status=200, is_bearish=False, **kwargs):
    with patch.object(rss.requests, "get", return_value=_resp(status, text)) as get:
        rows = _selector(**kwargs)._fetch_finviz_elite(INDUSTRY, 10, is_bearish)
    return rows, get


@pytest.mark.parametrize(
    "is_bearish,perf",
    [(False, "ta_perf2_4wup"), (True, "ta_perf2_4wdown")],
)
def test_request_targets_new_endpoint_with_type_and_pinned_columns(is_bearish, perf):
    _, get = _fetch(CSV_PINNED_WITH_VOLUME, is_bearish=is_bearish)
    args, kwargs = get.call_args
    assert args[0] == "https://elite.finviz.com/export/screener"
    assert "?" not in args[0], "query must go through params=, not the URL string"
    params = kwargs["params"]
    assert params == {
        "type": "stocks",
        "v": "151",
        "f": f"ind_semiconductors,cap_smallover,sh_avgvol_o100,sh_price_o10,{perf}",
        "c": "1,6,66,67",
        "ft": "4",
        "auth": SECRET,
    }
    assert kwargs["timeout"] == 15


@pytest.mark.parametrize("min_cap,cap_code", [("micro", "cap_microover"), ("mid", "cap_midover")])
def test_filter_string_follows_min_cap(min_cap, cap_code):
    _, get = _fetch(CSV_PINNED, min_cap=min_cap)
    assert get.call_args[1]["params"]["f"].split(",")[1] == cap_code


@pytest.mark.parametrize(
    "text",
    [CSV_LEGACY_18, CSV_PINNED, CSV_PINNED_WITH_NO, CSV_REORDERED, "﻿" + CSV_PINNED],
    ids=["legacy-18-cols", "pinned", "pinned-with-No", "reordered", "utf8-bom"],
)
def test_parsed_rows_are_independent_of_column_layout(text):
    rows, _ = _fetch(text)
    assert [(r["symbol"], r["market_cap"], r["change"]) for r in rows] == EXPECTED
    assert all(r["volume"] == _parse_volume(None) for r in rows)
    assert all(r["source"] == "finviz_elite" for r in rows)


def test_api_key_never_logged_on_request_exception(caplog):
    url_with_key = f"https://elite.finviz.com/export/screener?auth={SECRET}"
    with caplog.at_level(logging.DEBUG):
        with patch.object(rss.requests, "get", side_effect=RuntimeError(url_with_key)):
            assert _selector()._fetch_finviz_elite(INDUSTRY, 10, False) == []
    assert SECRET not in caplog.text


@pytest.mark.parametrize("status", [401, 403, 500])
def test_api_key_never_logged_on_http_error(status, caplog):
    with caplog.at_level(logging.DEBUG):
        rows, _ = _fetch("", status=status)
    assert rows == []
    assert SECRET not in caplog.text


def test_missing_ranked_column_is_warned_not_silent(caplog):
    with caplog.at_level(logging.WARNING, logger=rss.logger.name):
        rows, _ = _fetch("No.,Ticker\n1,AAA\n")
    assert [r["symbol"] for r in rows] == ["AAA"]
    assert all(column in caplog.text for column in ("Market Cap", "Change", "Volume"))
    assert SECRET not in caplog.text


def test_complete_columns_emit_no_missing_column_warning(caplog):
    with caplog.at_level(logging.WARNING, logger=rss.logger.name):
        _fetch(CSV_PINNED_WITH_VOLUME)
    assert "missing column" not in caplog.text
