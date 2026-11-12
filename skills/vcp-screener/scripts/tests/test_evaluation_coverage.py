"""Offline regressions for unknown VCP screening results (issue #711)."""

import json
import sys
from types import SimpleNamespace

import pytest
import screen_vcp
from coverage_client import CoverageFMPClient


def quote(price=50):
    return {"price": price, "yearHigh": 60, "yearLow": 20, "volume": 500000}


def history():
    return [
        {"close": 100 - i * 0.1, "high": 102 - i * 0.1, "low": 98 - i * 0.1, "volume": 500000}
        for i in range(260)
    ]


def run_screen(monkeypatch, tmp_path, quotes, histories=None, failures=None, limit=100):
    histories = histories or {}
    client = SimpleNamespace(
        get_batch_quotes=lambda symbols: {s: quotes[s] for s in symbols if quotes[s]},
        get_historical_prices=lambda symbol, days: {"historical": histories.get(symbol, [])},
        get_api_stats=lambda: {"api_calls_made": 0, "cache_entries": 0},
        coverage_failures=failures or {},
    )
    monkeypatch.setattr(screen_vcp, "FMPClient", lambda **kwargs: client)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "screen_vcp.py",
            "--universe",
            *quotes,
            "--max-candidates",
            str(limit),
            "--output-dir",
            str(tmp_path),
        ],
    )
    screen_vcp.main()
    report = json.loads(next(tmp_path.glob("vcp_screener_*.json")).read_text())
    markdown = next(tmp_path.glob("vcp_screener_*.md")).read_text()
    return report, markdown


def test_all_quotes_unavailable_are_not_a_zero_opportunity_result(monkeypatch, tmp_path, capsys):
    report, markdown = run_screen(monkeypatch, tmp_path, {"AAA": None, "BBB": None})
    coverage = report["evaluation_coverage"]
    assert coverage == {
        "schema_version": "1.0",
        "universe_size": 2,
        "evaluated": 0,
        "not_evaluated": 2,
        "not_evaluated_reasons": {"missing_data": 2},
        "verdict": "not_evaluable",
    }
    assert "0/2 evaluated" in markdown
    assert "undetermined" in markdown.lower()
    assert "No VCP candidates found" not in capsys.readouterr().out
    assert "No actionable pre-breakout candidates found." not in markdown


def test_valid_prefilter_rejections_are_evaluated(monkeypatch, tmp_path):
    report, markdown = run_screen(monkeypatch, tmp_path, {"AAA": quote(5), "BBB": quote(6)})
    assert report["evaluation_coverage"]["verdict"] == "complete"
    assert report["evaluation_coverage"]["evaluated"] == 2
    assert report["evaluation_coverage"]["not_evaluated_reasons"] == {}
    assert "2/2 evaluated" in markdown
    assert "No actionable pre-breakout candidates found." in markdown


def test_partial_quotes_leave_zero_candidate_conclusion_undetermined(monkeypatch, tmp_path):
    report, markdown = run_screen(monkeypatch, tmp_path, {"AAA": quote(5), "BBB": None})
    assert report["evaluation_coverage"]["verdict"] == "partial"
    assert report["evaluation_coverage"]["evaluated"] == 1
    assert "undetermined" in markdown.lower()


def test_complete_analysis_counts_a_member_once(monkeypatch, tmp_path):
    data = {"price": 100, "yearHigh": 105, "yearLow": 50, "volume": 500000}
    report, _ = run_screen(
        monkeypatch,
        tmp_path,
        {"AAA": data},
        {"SPY": history(), "AAA": history()},
    )
    assert report["evaluation_coverage"]["verdict"] == "complete"
    assert report["evaluation_coverage"]["evaluated"] == 1
    assert len(report["results"]) == 1


@pytest.mark.parametrize("failure", ["missing_data", "provider_error", "plan_gated"])
def test_unavailable_quote_reasons_are_counted(monkeypatch, tmp_path, failure):
    report, _ = run_screen(
        monkeypatch,
        tmp_path,
        {"AAA": None},
        failures={("quote", "AAA"): failure},
    )
    assert report["evaluation_coverage"]["not_evaluated_reasons"] == {failure: 1}


def test_candidate_cap_is_not_reported_as_complete_coverage(monkeypatch, tmp_path):
    monkeypatch.setattr(screen_vcp, "passes_trend_filter", lambda *args: False)
    report, _ = run_screen(
        monkeypatch,
        tmp_path,
        {"AAA": quote(), "BBB": quote()},
        {"SPY": history(), "AAA": history()},
        limit=1,
    )
    assert report["evaluation_coverage"]["evaluated"] == 1
    assert report["evaluation_coverage"]["not_evaluated_reasons"] == {"candidate_limit": 1}
    assert report["evaluation_coverage"]["verdict"] == "partial"


@pytest.mark.parametrize("bars", [[], history()[:100]])
def test_missing_or_short_history_is_not_a_failed_trend_decision(monkeypatch, tmp_path, bars):
    report, _ = run_screen(
        monkeypatch,
        tmp_path,
        {"AAA": quote()},
        {"SPY": history(), "AAA": bars},
    )
    assert report["evaluation_coverage"]["verdict"] == "not_evaluable"
    assert report["evaluation_coverage"]["not_evaluated_reasons"] == {
        "insufficient_history" if bars else "missing_data": 1,
    }


def test_missing_quote_field_is_unknown_not_a_prefilter_rejection(monkeypatch, tmp_path):
    data = quote()
    del data["yearHigh"]
    report, _ = run_screen(monkeypatch, tmp_path, {"AAA": data})
    assert report["evaluation_coverage"]["verdict"] == "not_evaluable"


def test_missing_benchmark_cannot_be_used_as_zero_relative_strength(monkeypatch, tmp_path):
    report, _ = run_screen(monkeypatch, tmp_path, {"AAA": quote()}, {"AAA": history()})
    assert report["evaluation_coverage"]["not_evaluated_reasons"] == {"benchmark_unavailable": 1}


@pytest.mark.parametrize("status,reason", [(402, "plan_gated"), (500, "provider_error")])
def test_real_client_failure_survives_legacy_fallback(monkeypatch, tmp_path, status, reason):
    client = CoverageFMPClient(api_key="fictional-key")  # pragma: allowlist secret
    client.RATE_LIMIT_DELAY = 0
    calls = []

    def response(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(
            status_code=status if "/stable/" in url else 403,
            text="fixture refusal",
            json=lambda: None,
        )

    monkeypatch.setattr(client.session, "get", response)
    monkeypatch.setattr(screen_vcp, "FMPClient", lambda **kwargs: client)
    monkeypatch.setattr(
        sys, "argv", ["screen_vcp.py", "--universe", "AAA", "BBB", "--output-dir", str(tmp_path)]
    )
    screen_vcp.main()
    report = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert report["evaluation_coverage"]["verdict"] == "not_evaluable"
    assert report["evaluation_coverage"]["not_evaluated_reasons"] == {reason: 2}
    assert len(calls) == 2  # no benchmark fetch when no symbols passed the quote stage
    assert "fictional-key" not in json.dumps(report)


def test_successful_fallback_does_not_count_as_unavailable(monkeypatch):
    client = CoverageFMPClient(api_key="fictional-key")  # pragma: allowlist secret
    client.RATE_LIMIT_DELAY = 0
    data = [{"symbol": "AAA", **quote()}]
    monkeypatch.setattr(
        client.session,
        "get",
        lambda url, **kwargs: SimpleNamespace(
            status_code=402 if "/stable/" in url else 200,
            text="fixture",
            json=lambda: data,
        ),
    )
    assert client.get_batch_quotes(["AAA"]) == {"AAA": data[0]}
    assert client.coverage_failures == {}


@pytest.mark.parametrize("field,value", [("close", None), ("high", float("nan")), ("volume", -1)])
def test_invalid_history_cannot_be_counted_as_evaluated(monkeypatch, tmp_path, field, value):
    bars = history()
    bars[0][field] = value
    report, _ = run_screen(
        monkeypatch,
        tmp_path,
        {"AAA": quote()},
        {"AAA": bars, "SPY": history()},
    )
    assert report["evaluation_coverage"]["verdict"] == "not_evaluable"
