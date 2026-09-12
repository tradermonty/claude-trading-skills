"""Tests for macro_regime_detector.py CLI behavior."""

import json
import sys
from unittest.mock import MagicMock, patch

import macro_regime_detector
import pytest


def test_output_dir_created_when_missing(tmp_path, monkeypatch):
    """--output-dir に存在しないパスを渡しても FileNotFoundError が出ないこと"""
    new_dir = tmp_path / "nonexistent"
    assert not new_dir.exists()

    _fake_comp = {
        "score": 10,
        "signal": "No data",
        "data_available": True,
        "direction": "stable",
        "roc_3m": 0.0,
        "roc_12m": 0.0,
        "crossover": {"type": "none", "bars_ago": None},
        "momentum_qualifier": "",
    }

    monkeypatch.setattr(
        sys,
        "argv",
        ["macro_regime_detector.py", "--api-key", "FAKE_KEY", "--output-dir", str(new_dir)],
    )

    mock_client = MagicMock()
    mock_client.get_historical_prices.return_value = {
        "historical": [{"date": "2026-01-01", "close": 100.0}]
    }
    mock_client.get_treasury_rates.return_value = None
    mock_client.get_api_stats.return_value = {"api_calls_made": 0, "cache_entries": 0}
    mock_client.get_data_mode.return_value = "yfinance_only"

    with (
        patch("macro_regime_detector.missing_required_packages", return_value=[]),
        patch("macro_regime_detector.FMPClient", return_value=mock_client),
        patch("macro_regime_detector.calculate_concentration", return_value=_fake_comp),
        patch("macro_regime_detector.calculate_yield_curve", return_value=_fake_comp),
        patch("macro_regime_detector.calculate_credit_conditions", return_value=_fake_comp),
        patch("macro_regime_detector.calculate_size_factor", return_value=_fake_comp),
        patch("macro_regime_detector.calculate_equity_bond", return_value=_fake_comp),
        patch("macro_regime_detector.calculate_sector_rotation", return_value=_fake_comp),
    ):
        macro_regime_detector.main()

    assert new_dir.exists()
    report = json.loads(next(new_dir.glob("macro_regime_*.json")).read_text(encoding="utf-8"))
    assert report["metadata"]["data_source"] == "yfinance"
    assert report["metadata"]["data_mode"] == "yfinance_only"


def test_zero_available_components_fail_closed_without_reports(tmp_path, monkeypatch, capsys):
    """A SPY-only response must reach and trip the 0/6 component guard."""
    output_dir = tmp_path / "reports"
    monkeypatch.setattr(
        sys,
        "argv",
        ["macro_regime_detector.py", "--api-key", "FAKE_KEY", "--output-dir", str(output_dir)],
    )

    mock_client = MagicMock()
    mock_client.get_historical_prices.side_effect = lambda symbol, days: (
        {"historical": [{"date": "2026-01-01", "close": 100.0}]} if symbol == "SPY" else None
    )
    mock_client.get_treasury_rates.return_value = None
    mock_client.get_api_stats.return_value = {"api_calls_made": 1, "cache_entries": 1}
    mock_client.get_data_mode.return_value = "fmp_with_yfinance_fallback"
    unavailable = {
        "score": 0,
        "signal": "INSUFFICIENT DATA: unavailable",
        "data_available": False,
        "direction": "unknown",
    }

    with (
        patch("macro_regime_detector.missing_required_packages", return_value=[]),
        patch("macro_regime_detector.FMPClient", return_value=mock_client),
        patch("macro_regime_detector.calculate_concentration", return_value=unavailable),
        patch("macro_regime_detector.calculate_yield_curve", return_value=unavailable),
        patch("macro_regime_detector.calculate_credit_conditions", return_value=unavailable),
        patch("macro_regime_detector.calculate_size_factor", return_value=unavailable),
        patch("macro_regime_detector.calculate_equity_bond", return_value=unavailable),
        patch("macro_regime_detector.calculate_sector_rotation", return_value=unavailable),
        patch("macro_regime_detector.classify_regime") as classify_regime,
        patch("macro_regime_detector.generate_json_report") as generate_json,
        patch("macro_regime_detector.generate_markdown_report") as generate_markdown,
        pytest.raises(SystemExit) as exc_info,
    ):
        macro_regime_detector.main()

    assert exc_info.value.code == 1
    assert (
        "No macro-regime components have usable data; refusing to classify or write reports."
        in capsys.readouterr().err
    )
    classify_regime.assert_not_called()
    generate_json.assert_not_called()
    generate_markdown.assert_not_called()
    assert not list(tmp_path.rglob("macro_regime_*.json"))
    assert not list(tmp_path.rglob("macro_regime_*.md"))
