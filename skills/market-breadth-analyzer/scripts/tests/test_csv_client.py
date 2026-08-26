"""Behavioral tests for the market breadth CSV client."""

from datetime import datetime
from unittest.mock import Mock

import csv_client
import pytest
import requests

DETAIL_HEADER = ",".join(csv_client.DETAIL_COLUMNS)


def _response(text="", *, headers=None):
    response = Mock()
    response.text = text
    response.headers = headers or {}
    return response


def _detail_row(date, *, price="5000", bearish="false", peak="0"):
    return ",".join(
        [
            date,
            price,
            "0.50",
            "0.45",
            "0.55",
            "1",
            bearish,
            peak,
            "no",
            "yes",
        ]
    )


def test_fetch_detail_csv_parses_types_and_sorts_rows(monkeypatch):
    response = _response(
        "\n".join(
            [
                DETAIL_HEADER,
                _detail_row("2025-01-02", bearish="yes"),
                _detail_row("2025-01-01", price="4990.5", peak="true"),
            ]
        )
    )
    monkeypatch.setattr(csv_client.requests, "get", Mock(return_value=response))

    rows = csv_client.fetch_detail_csv("https://example.test/detail.csv")

    assert [row["Date"] for row in rows] == ["2025-01-01", "2025-01-02"]
    assert rows[0]["S&P500_Price"] == 4990.5
    assert rows[0]["Breadth_200MA_Trend"] == 1
    assert rows[0]["Is_Peak"] is True
    assert rows[0]["Is_Trough"] is False
    assert rows[1]["Bearish_Signal"] is True
    response.raise_for_status.assert_called_once_with()


def test_fetch_detail_csv_skips_bad_rows_and_reports_line(monkeypatch, capsys):
    response = _response(
        "\n".join(
            [
                DETAIL_HEADER,
                _detail_row("2025-01-01", price="not-a-number"),
                _detail_row("2025-01-02"),
            ]
        )
    )
    monkeypatch.setattr(csv_client.requests, "get", Mock(return_value=response))

    rows = csv_client.fetch_detail_csv("https://example.test/detail.csv")

    assert [row["Date"] for row in rows] == ["2025-01-02"]
    assert "WARN: Skipping line 2" in capsys.readouterr().err


@pytest.mark.parametrize(
    "body",
    [
        DETAIL_HEADER,
        "\n".join([DETAIL_HEADER, _detail_row("2025-01-01", price="bad")]),
        "\n".join([DETAIL_HEADER, "2025-01-01"]),
    ],
)
def test_fetch_detail_csv_returns_empty_when_no_valid_rows(monkeypatch, capsys, body):
    monkeypatch.setattr(csv_client.requests, "get", Mock(return_value=_response(body)))

    assert csv_client.fetch_detail_csv("https://example.test/detail.csv") == []
    assert "OK (0 rows)" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("column", "value", "warning"),
    [
        ("Date", "2025-02-30", "invalid Date"),
        ("Date", "2026-1-5", "invalid Date"),
        ("S&P500_Price", "nan", "must be finite"),
        ("Breadth_Index_Raw", "inf", "must be finite"),
        ("Breadth_Index_200MA", "-inf", "must be finite"),
        ("Bearish_Signal", "unknown", "invalid boolean value"),
    ],
)
def test_fetch_detail_csv_rejects_semantically_invalid_rows(
    monkeypatch,
    capsys,
    column,
    value,
    warning,
):
    values = _detail_row("2025-01-01").split(",")
    values[list(csv_client.DETAIL_COLUMNS).index(column)] = value
    body = "\n".join([DETAIL_HEADER, ",".join(values)])
    monkeypatch.setattr(csv_client.requests, "get", Mock(return_value=_response(body)))

    assert csv_client.fetch_detail_csv("https://example.test/detail.csv") == []
    captured = capsys.readouterr()
    assert warning in captured.err
    assert "OK (0 rows)" in captured.out


def test_fetch_detail_csv_transport_error_fails_closed(monkeypatch, capsys):
    monkeypatch.setattr(
        csv_client.requests,
        "get",
        Mock(side_effect=requests.RequestException("offline")),
    )

    assert csv_client.fetch_detail_csv("https://example.test/detail.csv") == []
    assert "Failed to fetch detail CSV: offline" in capsys.readouterr().err


def test_fetch_summary_csv_maps_metrics_and_skips_blank_names(monkeypatch):
    response = _response("Metric,Value\nAverage Peak,0.75\n,ignored\nCurrent,0.55\n")
    monkeypatch.setattr(csv_client.requests, "get", Mock(return_value=response))

    assert csv_client.fetch_summary_csv("https://example.test/summary.csv") == {
        "Average Peak": "0.75",
        "Current": "0.55",
    }
    response.raise_for_status.assert_called_once_with()


def test_fetch_summary_csv_skips_truncated_rows(monkeypatch, capsys):
    response = _response("Metric,Value\nBroken\nCurrent,0.55\n")
    monkeypatch.setattr(csv_client.requests, "get", Mock(return_value=response))

    assert csv_client.fetch_summary_csv("https://example.test/summary.csv") == {"Current": "0.55"}
    assert "WARN: Skipping summary line 2: truncated row" in capsys.readouterr().err


def test_fetch_summary_csv_transport_error_returns_empty(monkeypatch, capsys):
    monkeypatch.setattr(
        csv_client.requests,
        "get",
        Mock(side_effect=requests.RequestException("offline")),
    )

    assert csv_client.fetch_summary_csv("https://example.test/summary.csv") == {}
    assert "Failed to fetch summary CSV: offline" in capsys.readouterr().err


def test_check_data_freshness_handles_missing_and_invalid_dates():
    assert csv_client.check_data_freshness([]) == {
        "is_fresh": False,
        "latest_date": None,
        "days_old": None,
        "last_modified": None,
        "warning": "No data available",
    }

    result = csv_client.check_data_freshness([{"Date": "not-a-date"}])
    assert result["is_fresh"] is False
    assert result["days_old"] is None
    assert result["warning"] == "Cannot parse latest date: not-a-date"


@pytest.mark.parametrize(
    ("latest_date", "max_stale_days", "expected_fresh", "expected_days"),
    [
        ("2025-01-08", 5, True, 2),
        ("2025-01-01", 5, False, 9),
    ],
)
def test_check_data_freshness_is_deterministic(
    monkeypatch,
    latest_date,
    max_stale_days,
    expected_fresh,
    expected_days,
):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2025, 1, 10)

    monkeypatch.setattr(csv_client, "datetime", FixedDateTime)
    monkeypatch.setattr(csv_client, "_check_last_modified", Mock(return_value="2025-01-09"))

    result = csv_client.check_data_freshness(
        [{"Date": latest_date}],
        max_stale_days=max_stale_days,
        detail_url="https://example.test/detail.csv",
    )

    assert result["is_fresh"] is expected_fresh
    assert result["days_old"] == expected_days
    assert result["last_modified"] == "2025-01-09"
    assert (result["warning"] is None) is expected_fresh


def test_check_last_modified_formats_header_and_swallows_head_failure(monkeypatch):
    response = _response(headers={"Last-Modified": "Wed, 08 Jan 2025 12:30:00 GMT"})
    head = Mock(return_value=response)
    monkeypatch.setattr(csv_client.requests, "head", head)

    assert csv_client._check_last_modified("https://example.test/detail.csv") == (
        "2025-01-08 12:30 UTC"
    )
    head.assert_called_once_with(
        "https://example.test/detail.csv", timeout=10, allow_redirects=True
    )

    head.side_effect = requests.RequestException("offline")
    assert csv_client._check_last_modified("https://example.test/detail.csv") is None
