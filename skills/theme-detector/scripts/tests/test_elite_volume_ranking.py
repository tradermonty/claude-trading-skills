"""#800: FINVIZ must deliver Volume through the real selector request path."""

import csv
import io
import logging
from unittest.mock import MagicMock, patch

import pytest
import representative_stock_selector as rss

SECRET = "fictional-issue800-key"  # pragma: allowlist secret
INDUSTRY = "Semiconductors"


def _csv(volumes=None, bearish=False):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["Ticker", "Market Cap", "Change"] + (["Volume"] if volumes is not None else [])
    )
    for i, (symbol, cap, change) in enumerate([("LOWVOL", "2000", 4), ("HIGHVOL", "1000", 5)]):
        row = [symbol, cap, f"{-change if bearish else change}.00%"]
        writer.writerow(row + ([volumes[i]] if volumes is not None else []))
    return output.getvalue()


def _selector():
    return rss.RepresentativeStockSelector(
        finviz_elite_key=SECRET, finviz_mode="elite", rate_limit_sec=0
    )


def _server(bearish=False):
    def get(url, params, timeout):
        assert url == "https://elite.finviz.com/export/screener"
        # Simulate the provider's explicit projection, rather than giving the
        # parser Volume regardless of whether the production request asks for it.
        volumes = ["100,000", "9,000,000"] if "67" in params["c"].split(",") else None
        return MagicMock(status_code=200, text=_csv(volumes, bearish))

    return get


@pytest.mark.parametrize("bearish", [False, True])
def test_full_selector_ranking_changes_when_request_adds_volume(monkeypatch, bearish):
    theme = {
        "matching_industries": [{"name": INDUSTRY}],
        "direction": "bearish" if bearish else "bullish",
    }
    with patch.object(rss.requests, "get", side_effect=_server(bearish)) as get:
        with monkeypatch.context() as legacy:
            legacy.setattr(rss, "FINVIZ_ELITE_EXPORT_COLUMNS", "1,6,66")
            before = _selector().select_stocks(theme, max_stocks=2)
        after = _selector().select_stocks(theme, max_stocks=2)
    assert [(s["symbol"], s["composite_score"]) for s in before] == [
        ("LOWVOL", 0.7857),
        ("HIGHVOL", 0.7143),
    ]
    assert [(s["symbol"], s["composite_score"]) for s in after] == [
        ("HIGHVOL", 0.8),
        ("LOWVOL", 0.7),
    ]
    assert [s["volume"] for s in after] == [9_000_000, 100_000]
    assert [s["market_cap"] for s in after] == [1_000_000_000, 2_000_000_000]
    assert all(s["source"] == "finviz_elite" for s in after)
    assert get.call_args_list[0].kwargs["params"]["c"] == "1,6,66"
    assert get.call_args_list[1].kwargs["params"]["c"] == "1,6,66,67"
    filters = get.call_args.kwargs["params"]["f"].split(",")
    assert ("ta_perf2_4wdown" if bearish else "ta_perf2_4wup") in filters


def test_missing_volume_header_warns_before_renormalizing(caplog):
    with patch.object(rss.requests, "get", return_value=MagicMock(status_code=200, text=_csv())):
        with caplog.at_level(logging.WARNING, logger=rss.logger.name):
            selector = _selector()
            rows = selector._fetch_finviz_elite(INDUSTRY, 10, False)
    assert len(rows) == 2 and all(s["volume"] is None for s in rows)
    assert "missing column(s): Volume" in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "-",
        "bad",
        "-1",
        "-0.1",
        "-0.000001",
        "-0.0000001M",
        "-1e-999",
        "NaN",
        "Infinity",
        "1e309",
        "1e309M",
    ],
)
def test_invalid_volume_preserves_rows_and_warns_without_echo(bad, caplog):
    text = _csv([bad, "9,000,000"])
    with patch.object(rss.requests, "get", return_value=MagicMock(status_code=200, text=text)):
        with caplog.at_level(logging.WARNING, logger=rss.logger.name):
            selector = _selector()
            rows = selector._fetch_finviz_elite(INDUSTRY, 10, False)
    assert [s["symbol"] for s in rows] == ["LOWVOL", "HIGHVOL"]
    assert [s["volume"] for s in rows] == [None, 9_000_000]
    assert selector.failure_count == 0
    assert len(caplog.records) == 1
    assert "unavailable Volume for 1 row(s)" in caplog.text
    assert "re-normalized" in caplog.text
    assert SECRET not in caplog.text


def test_unknown_volume_for_every_row_is_visible_and_renormalized(caplog):
    text = _csv(["-", "-"])
    with patch.object(rss.requests, "get", return_value=MagicMock(status_code=200, text=text)):
        with caplog.at_level(logging.WARNING, logger=rss.logger.name):
            selector = _selector()
            stocks = selector.select_stocks({"matching_industries": [{"name": INDUSTRY}]}, 2)
    assert [(s["symbol"], s["composite_score"]) for s in stocks] == [
        ("LOWVOL", 0.7857),
        ("HIGHVOL", 0.7143),
    ]
    assert "unavailable Volume for 2 row(s)" in caplog.text


@pytest.mark.parametrize(
    "volume,expected",
    [
        ("0", 0),
        ("-0.0", 0),
        ("0M", 0),
        ("1234567", 1_234_567),
        ("1,234,567", 1_234_567),
        ("1.2M", 1_200_000),
    ],
)
def test_valid_volume_formats_are_available_without_warning(volume, expected, caplog):
    with patch.object(
        rss.requests, "get", return_value=MagicMock(status_code=200, text=_csv([volume, volume]))
    ):
        with caplog.at_level(logging.WARNING, logger=rss.logger.name):
            rows = _selector()._fetch_finviz_elite(INDUSTRY, 10, False)
    assert [s["volume"] for s in rows] == [expected, expected]
    assert not caplog.records


@pytest.mark.parametrize("transform", ["plain", "leading-no", "reordered", "bom"])
def test_four_column_csv_layouts_preserve_all_ranking_values(transform):
    text = _csv(["100,000", "9,000,000"])
    if transform == "leading-no":
        rows = list(csv.reader(io.StringIO(text)))
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["No.", *rows[0]])
        for i, row in enumerate(rows[1:], 1):
            writer.writerow([i, *row])
        text = output.getvalue()
    elif transform == "reordered":
        rows = list(csv.reader(io.StringIO(text)))
        output = io.StringIO()
        csv.writer(output).writerows([[row[3], row[2], row[0], row[1]] for row in rows])
        text = output.getvalue()
    elif transform == "bom":
        text = "\ufeff" + text
    with patch.object(rss.requests, "get", return_value=MagicMock(status_code=200, text=text)):
        rows = _selector()._fetch_finviz_elite(INDUSTRY, 10, False)
    assert [(s["symbol"], s["market_cap"], s["change"], s["volume"]) for s in rows] == [
        ("LOWVOL", 2_000_000_000, 4.0, 100_000),
        ("HIGHVOL", 1_000_000_000, 5.0, 9_000_000),
    ]
