"""Authenticated groups preserve units and never expose credentials (#671)."""

import csv
import io
import sys
from unittest.mock import Mock

import finviz_performance_client as client
import pandas as pd
import pytest
import requests
import theme_detector

KEY = "FICTIONAL-GROUP-KEY"  # pragma: allowlist secret
HEADERS = [
    "Name",
    "Performance (Week)",
    "Performance (Month)",
    "Performance (Quarter)",
    "Performance (Half Year)",
    "Performance (Year)",
    "Performance (Year To Date)",
]


def csv_body(values=None):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(HEADERS)
    writer.writerow(
        [
            "Fictional Industry",
            *(values if values is not None else ["5%", "0.12%", "-0.12%", "0%", "10.5%", "2"]),
        ]
    )
    return stream.getvalue()


@pytest.fixture
def public(monkeypatch):
    monkeypatch.delenv("FINVIZ_API_KEY", raising=False)
    monkeypatch.setattr(client, "HAS_FINVIZFINANCE", True)
    perf = Mock()
    perf.screener_view.return_value = pd.DataFrame(
        [{"Name": "Public Industry", "Perf Week": 0.05, "Perf Month": 0.02}]
    )
    module = Mock()
    module.Performance.return_value = perf
    monkeypatch.setattr(client, "fvperf", module, raising=False)
    return perf


@pytest.fixture
def http(monkeypatch):
    get = Mock(return_value=Mock(status_code=200, text=csv_body()))
    monkeypatch.setattr(requests, "get", get)
    return get


@pytest.mark.parametrize(
    "group,fetch",
    [("industry", client.get_industry_performance), ("sector", client.get_sector_performance)],
)
def test_elite_success_without_public_library(group, fetch, monkeypatch, http, public):
    monkeypatch.setattr(client, "HAS_FINVIZFINANCE", False)
    rows = fetch(api_key=KEY)
    assert rows[0]["name"] == "Fictional Industry"
    assert rows[0]["perf_1w"] == 0.05
    assert rows[0]["perf_1m"] == 0.0012
    assert rows[0]["perf_3m"] == -0.0012
    assert rows[0]["perf_6m"] == 0
    assert rows[0]["perf_ytd"] == 0.02
    percent = theme_detector._convert_perf_to_pct(rows)[0]
    assert percent["perf_1m"] == pytest.approx(0.12)
    assert percent["perf_3m"] == pytest.approx(-0.12)
    http.assert_called_once_with(
        "https://elite.finviz.com/grp_export",
        params={"g": group, "v": "140", "o": "name", "auth": KEY},
        timeout=15,
        allow_redirects=False,
    )
    public.screener_view.assert_not_called()


@pytest.mark.skipif(sys.version_info < (3, 10), reason="public fallback requires Python3.10+")
def test_environment_key_and_explicit_public_override(monkeypatch, http, public):
    monkeypatch.setenv("FINVIZ_API_KEY", KEY)
    assert client.get_industry_performance()[0]["name"] == "Fictional Industry"
    http.reset_mock()
    assert client.get_industry_performance(api_key="")[0]["name"] == "Public Industry"
    http.assert_not_called()
    public.screener_view.assert_called_once_with(group="Industry")


@pytest.mark.skipif(sys.version_info < (3, 10), reason="public fallback requires Python3.10+")
@pytest.mark.parametrize(
    "failure", ["http", "timeout", "html", "empty", "headers", "all-null", "nan", "inf", "invalid"]
)
def test_failed_elite_falls_back_without_key_or_payload_leak(
    failure, monkeypatch, http, public, capsys
):
    marker = "UNTRUSTED-BODY-" + KEY
    if failure == "timeout":
        http.side_effect = requests.Timeout(marker)
    elif failure == "http":
        http.return_value = Mock(status_code=403, text=marker)
    else:
        body = {
            "html": f"<html>{marker}</html>",
            "empty": "",
            "headers": "Name,Old Column\n" + marker + ",1\n",
            "all-null": csv_body(["-"] * 6),
            "nan": csv_body(["nan"] * 6),
            "inf": csv_body(["inf"] * 6),
            "invalid": csv_body([marker] * 6),
        }[failure]
        http.return_value = Mock(status_code=200, text=body)
    rows = client.get_industry_performance(api_key=KEY)
    assert rows[0]["name"] == "Public Industry"
    public.screener_view.assert_called_once()
    output = capsys.readouterr()
    assert KEY not in output.out + output.err
    assert marker not in output.out + output.err
    assert "public" in output.err.lower()


def test_both_sources_fail_with_actionable_safe_guidance(http, public, capsys):
    http.side_effect = requests.Timeout(KEY)
    public.screener_view.side_effect = RuntimeError(KEY)
    assert client.get_industry_performance(api_key=KEY) == []
    output = capsys.readouterr()
    assert KEY not in output.out + output.err
    assert "1.5.0" in output.err
    assert "3.10" in output.err
    assert "FINVIZ_API_KEY" in output.err


def test_finvizfinance_absence_keeps_elite_path(http, monkeypatch, capsys):
    monkeypatch.setattr(client, "HAS_FINVIZFINANCE", False)
    http.return_value = Mock(status_code=403, text=KEY)
    assert client.get_industry_performance(api_key=KEY) == []
    assert "FINVIZ_API_KEY" in capsys.readouterr().err


def test_public_path_is_disabled_on_python39_even_with_old_library(
    monkeypatch, public, http, capsys
):
    monkeypatch.setattr(client.sys, "version_info", (3, 9, 23))
    assert client.get_industry_performance(api_key="") == []
    public.screener_view.assert_not_called()
    http.assert_not_called()
    assert "3.10" in capsys.readouterr().err


@pytest.mark.parametrize(
    "mode,explicit_key,expected_key",
    [
        ("elite", None, KEY),
        ("elite", "CLI-KEY", "CLI-KEY"),
        ("public", None, None),
        ("public", "CLI-KEY", None),
    ],
)
def test_main_routes_resolved_key_and_public_override(
    tmp_path, monkeypatch, http, mode, explicit_key, expected_key, capsys
):
    monkeypatch.setenv("FINVIZ_API_KEY", KEY)
    monkeypatch.setattr(client, "HAS_FINVIZFINANCE", False)
    http.return_value = Mock(status_code=403, text=KEY)
    argv = ["--finviz-mode", mode, "--output-dir", str(tmp_path)]
    if explicit_key is not None:
        argv += ["--finviz-api-key", explicit_key]
    with pytest.raises(SystemExit) as error:
        theme_detector.main(argv)
    assert error.value.code == 1
    if expected_key is None:
        http.assert_not_called()
    else:
        assert http.call_args.kwargs["params"]["auth"] == expected_key
    output = capsys.readouterr()
    assert KEY not in output.out + output.err
    assert "CLI-KEY" not in output.out + output.err
    assert "No industry data" in output.err
    assert "1.5.0" in output.err
    assert list(tmp_path.iterdir()) == []


def test_actual_finvizfinance15_public_parser_retains_decimal_units(monkeypatch):
    pytest.importorskip("finvizfinance", minversion="1.5.0")
    from bs4 import BeautifulSoup
    from finvizfinance.group import base, performance

    # The official parser removes the No. column and converts numeric columns.
    headers = [
        "No.",
        "Name",
        "Stocks",
        "Perf Week",
        "Perf Month",
        "Perf Quart",
        "Perf Half",
        "Perf Year",
        "Perf YTD",
    ]
    values = ["1", "Fictional", "10", "5%", "0.12%", "-0.12%", "0%", "10%", "2%"]
    html = (
        '<table class="groups_table"><tr>'
        + "".join(f"<th>{h}</th>" for h in headers)
        + "</tr><tr>"
        + "".join(f"<td>{v}</td>" for v in values)
        + "</tr></table>"
    )
    monkeypatch.setattr(base, "web_scrap", lambda *_a, **_kw: BeautifulSoup(html, "html.parser"))
    monkeypatch.setattr(client, "fvperf", performance)
    monkeypatch.setattr(client, "HAS_FINVIZFINANCE", True)
    result = client.get_industry_performance(api_key="")
    assert result[0]["perf_1m"] == 0.0012
    assert theme_detector._convert_perf_to_pct(result)[0]["perf_1m"] == pytest.approx(0.12)
