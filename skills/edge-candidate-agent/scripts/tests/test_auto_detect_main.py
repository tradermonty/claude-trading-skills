"""End-to-end tests for auto_detect_candidates.main() and write_outputs()."""

import json
from pathlib import Path
from subprocess import CompletedProcess

import auto_detect_candidates as adc
import pandas as pd
import pytest
import synthetic_ohlcv as so
import yaml

pytest.importorskip("pyarrow")


@pytest.fixture(scope="module")
def ohlcv(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("e2e") / "ohlcv.parquet"
    so.build_market().to_parquet(path)
    return path


def run_main(monkeypatch, *argv: str) -> int:
    monkeypatch.setattr("sys.argv", ["auto_detect_candidates.py", *argv])
    return adc.main()


def base_args(ohlcv: Path, out: Path) -> list[str]:
    return ["--ohlcv", str(ohlcv), "--output-dir", str(out)]


def load_tickets(directory: Path) -> dict[str, dict]:
    return {p.stem: yaml.safe_load(p.read_text()) for p in sorted(directory.glob("*.yaml"))}


def test_main_end_to_end_writes_all_artifacts(monkeypatch, capsys, ohlcv, tmp_path) -> None:
    out = tmp_path / "out"
    rc = run_main(monkeypatch, *base_args(ohlcv, out))
    stdout = capsys.readouterr().out
    assert rc == 0
    assert "[OK] as_of=2026-02-20 regime=RiskOn" in stdout
    research_files = list((out / "tickets" / "research_only").glob("*.yaml"))
    assert f"[OK] watchlist=3 exportable_tickets=4 research_tickets={len(research_files)}" in stdout
    # No news/futures input was given, so no ticket of those types may appear.
    assert not [p for p in research_files if "futures_trigger" in p.name]
    assert f"[OK] report={out / 'daily_report.md'}" in stdout
    assert "llm_hints_used" not in stdout

    summary = json.loads((out / "market_summary.json").read_text())
    assert summary["regime_label"] == "RiskOn"
    anomalies = json.loads((out / "anomalies.json").read_text())
    assert {"GAPPER", "PANIC", "BRK"} <= {a["symbol"] for a in anomalies}

    watchlist = pd.read_csv(out / "watchlist.csv")
    assert set(zip(watchlist["symbol"], watchlist["entry_family"])) == {
        ("BRK", "pivot_breakout"),
        ("GAPPER", "pivot_breakout"),
        ("GAPPER", "gap_up_continuation"),
    }

    tickets = load_tickets(out / "tickets" / "exportable")
    assert set(tickets) == {
        "edge_auto_vcp_brk_20260220",
        "edge_auto_vcp_gapper_20260220",
        "edge_auto_gap_gapper_20260220",
        "edge_auto_panic_reversal_panic_20260220",
    }
    panic = tickets["edge_auto_panic_reversal_panic_20260220"]
    assert panic["entry_family"] == "panic_reversal"
    assert panic["holding_horizon"] == "5D"
    assert panic["regime"] == "RiskOn"
    ranks = sorted(t["rank"] for t in tickets.values())
    assert ranks == [1, 2, 3, 4]

    manifest = json.loads((out / "run_manifest.json").read_text())
    assert manifest["as_of"] == "2026-02-20"
    assert manifest["exportable_ticket_count"] == 4
    assert manifest["skipped_modules"] == [
        "news_reaction(no_input)",
        "futures_trigger(no_input)",
    ]
    report = (out / "daily_report.md").read_text()
    assert "Optional modules skipped: news_reaction(no_input), futures_trigger(no_input)" in report
    assert "edge_auto_vcp_brk_20260220 | pivot_breakout" in report


def test_main_uses_hints_llm_news_and_futures(monkeypatch, capsys, ohlcv, tmp_path) -> None:
    hints = tmp_path / "hints.yaml"
    hints.write_text(
        yaml.safe_dump(
            {
                "hints": [
                    {
                        "title": "Leaders breaking out",
                        "symbols": ["BRK"],
                        "preferred_entry_family": "pivot_breakout",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    news = tmp_path / "news.csv"
    news.write_text(
        "symbol,timestamp,reaction_1d\nBRK,2026-02-20,0.10\nPANIC,2026-02-19,0.30\n",
        encoding="utf-8",
    )
    futures = tmp_path / "fut.csv"
    dates = pd.bdate_range(end="2026-02-20", periods=70, tz="UTC")
    closes = [100.0 * (1.001 ** (i % 3)) for i in range(70)]
    closes[-1] = closes[-2] * 1.06
    pd.DataFrame({"symbol": "ES", "timestamp": dates, "close": closes}).to_csv(futures, index=False)
    fmap = tmp_path / "map.yaml"
    fmap.write_text("mappings:\n  ES: [spy, brk]\n", encoding="utf-8")

    seen: dict = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["payload"] = json.loads(kwargs["input"])
        return CompletedProcess(
            cmd,
            0,
            stdout='[{"title": "LLM idea", "preferred_entry_family": "panic_reversal"}]',
            stderr="",
        )

    monkeypatch.setattr(adc.subprocess, "run", fake_run)
    out = tmp_path / "out"
    rc = run_main(
        monkeypatch,
        *base_args(ohlcv, out),
        "--hints",
        str(hints),
        "--llm-ideas-cmd",
        "fake-llm --json",
        "--news-reactions",
        str(news),
        "--futures-ohlcv",
        str(futures),
        "--futures-map",
        str(fmap),
        "--top-n",
        "1",
        "--top-research-n",
        "3",
        "--anomaly-top-k",
        "4",
    )
    stdout = capsys.readouterr().out
    assert rc == 0
    assert seen["cmd"] == ["fake-llm", "--json"]
    assert seen["payload"]["as_of"] == "2026-02-20"
    assert len(seen["payload"]["anomalies"]) == 4
    assert "[OK] llm_hints_used=1" in stdout

    manifest = json.loads((out / "run_manifest.json").read_text())
    assert manifest["skipped_modules"] == []
    assert manifest["watchlist_count"] == 3

    exportable = load_tickets(out / "tickets" / "exportable")
    # top-n=1 breakout ticket + PANIC reversal + BRK news reaction (PANIC news is not on the target date)
    assert set(exportable) == {
        "edge_auto_vcp_brk_20260220",
        "edge_auto_panic_reversal_panic_20260220",
        "edge_auto_news_reaction_brk_20260220",
    }
    assert exportable["edge_auto_vcp_brk_20260220"]["observation"]["matched_hints"] == [
        "Leaders breaking out"
    ]
    # The LLM panic hint is a generic hint, so the reversal ticket carries it.
    assert exportable["edge_auto_panic_reversal_panic_20260220"]["observation"][
        "matched_hints"
    ] == ["LLM idea"]
    news_ticket = exportable["edge_auto_news_reaction_brk_20260220"]
    assert news_ticket["observation"]["reaction_direction"] == "up"

    research = load_tickets(out / "tickets" / "research_only")
    assert {
        "edge_auto_futures_trigger_spy_20260220",
        "edge_auto_futures_trigger_brk_20260220",
    } <= set(research)
    assert len(research) <= 3
    assert all(t["research_only"] is True for t in research.values())
    assert len(json.loads((out / "anomalies.json").read_text())) == 4


@pytest.mark.parametrize(
    "flag,message",
    [
        ("--hints", "[ERROR] hints file not found"),
        ("--news-reactions", "[ERROR] news reactions file not found"),
        ("--futures-ohlcv", "[ERROR] futures OHLCV file not found"),
        ("--futures-map", "[ERROR] futures map file not found"),
    ],
)
def test_main_missing_optional_inputs(monkeypatch, capsys, ohlcv, tmp_path, flag, message) -> None:
    out = tmp_path / "out"
    rc = run_main(monkeypatch, *base_args(ohlcv, out), flag, str(tmp_path / "missing.file"))
    assert rc == 1
    assert message in capsys.readouterr().out
    assert not out.exists()


def test_main_missing_ohlcv(monkeypatch, capsys, tmp_path) -> None:
    rc = run_main(monkeypatch, "--ohlcv", str(tmp_path / "none.parquet"))
    assert rc == 1
    assert "[ERROR] OHLCV file not found" in capsys.readouterr().out


def test_main_invalid_as_of_is_reported_not_raised(monkeypatch, capsys, ohlcv, tmp_path) -> None:
    rc = run_main(monkeypatch, *base_args(ohlcv, tmp_path / "out"), "--as-of", "20260220")
    assert rc == 1
    assert "[ERROR] invalid --as-of format" in capsys.readouterr().out


def test_main_as_of_before_data_returns_error(monkeypatch, capsys, ohlcv, tmp_path) -> None:
    rc = run_main(monkeypatch, *base_args(ohlcv, tmp_path / "out"), "--as-of", "2001-01-02")
    assert rc == 1
    assert "[ERROR] no OHLCV data at or before as_of=2001-01-02" in capsys.readouterr().out


def test_main_as_of_selects_earlier_session(monkeypatch, capsys, ohlcv, tmp_path) -> None:
    out = tmp_path / "out"
    rc = run_main(monkeypatch, *base_args(ohlcv, out), "--as-of", "2026-02-12")
    assert rc == 0
    assert "[OK] as_of=2026-02-12" in capsys.readouterr().out
    assert json.loads((out / "market_summary.json").read_text())["as_of"] == "2026-02-12"
    # The final-day events (Feb 20) must not leak into an earlier as-of run.
    assert not list((out / "tickets" / "exportable").glob("*panic*"))


def test_main_returns_error_when_llm_command_fails(monkeypatch, capsys, ohlcv, tmp_path) -> None:
    monkeypatch.setattr(
        adc.subprocess, "run", lambda cmd, **k: CompletedProcess(cmd, 3, "", "llm exploded")
    )
    rc = run_main(monkeypatch, *base_args(ohlcv, tmp_path / "out"), "--llm-ideas-cmd", "bad-llm")
    assert rc == 1
    assert "[ERROR] LLM ideas command failed: llm exploded" in capsys.readouterr().out


def test_main_returns_error_for_invalid_news_schema(monkeypatch, capsys, ohlcv, tmp_path) -> None:
    news = tmp_path / "news.csv"
    news.write_text("symbol,when\nBRK,today\n", encoding="utf-8")
    rc = run_main(monkeypatch, *base_args(ohlcv, tmp_path / "out"), "--news-reactions", str(news))
    assert rc == 1
    assert (
        "news reactions file must include symbol,timestamp,reaction_1d" in capsys.readouterr().out
    )


def test_main_returns_error_for_invalid_hints_yaml(monkeypatch, capsys, ohlcv, tmp_path) -> None:
    hints = tmp_path / "hints.yaml"
    hints.write_text("a plain string\n", encoding="utf-8")
    rc = run_main(monkeypatch, *base_args(ohlcv, tmp_path / "out"), "--hints", str(hints))
    assert rc == 1
    assert "[ERROR] invalid hints format" in capsys.readouterr().out


def test_main_returns_error_when_no_symbol_is_tradable(
    monkeypatch, capsys, ohlcv, tmp_path
) -> None:
    rc = run_main(monkeypatch, *base_args(ohlcv, tmp_path / "out"), "--min-price", "1000000")
    assert rc == 1
    assert "[ERROR] no tradable symbols remain" in capsys.readouterr().out


# --- export integration ---------------------------------------------------------


def test_main_export_strategies_and_force(monkeypatch, capsys, ohlcv, tmp_path) -> None:
    out = tmp_path / "out"
    strategies = tmp_path / "strategies"
    args = [*base_args(ohlcv, out), "--export-strategies-dir", str(strategies)]
    assert run_main(monkeypatch, *args) == 0
    stdout = capsys.readouterr().out
    assert f"[OK] exported_strategies=4 dir={strategies}" in stdout
    dirs = sorted(p.name for p in strategies.iterdir())
    assert "edge_auto_panic_reversal_panic_20260220" in dirs
    spec = yaml.safe_load(
        (strategies / "edge_auto_gap_gapper_20260220" / "strategy.yaml").read_text()
    )
    assert spec["signals"]["entry"]["type"] == "gap_up_continuation"
    assert spec["signals"]["entry"]["conditions"][0] == "gap >= 4%"
    assert "gap_up_detection" in spec

    # Re-export without --force is refused and reported as an integration error.
    assert run_main(monkeypatch, *args) == 1
    assert "[ERROR] export/validation integration failed" in capsys.readouterr().out
    assert run_main(monkeypatch, *args, "--force-export") == 0


def test_main_pipeline_validation_pass_and_fail(monkeypatch, capsys, ohlcv, tmp_path) -> None:
    calls: list[tuple[str, str]] = []

    def validator(strategy_path, pipeline_root, stage):
        calls.append((strategy_path.parent.name, stage))
        return []

    monkeypatch.setattr("validate_candidate.validate_with_pipeline_schema", validator)
    args = [
        *base_args(ohlcv, tmp_path / "out"),
        "--export-strategies-dir",
        str(tmp_path / "s"),
        "--pipeline-root",
        str(tmp_path / "pipe"),
        "--pipeline-stage",
        "phase2",
    ]
    assert run_main(monkeypatch, *args) == 0
    assert (
        "pipeline validation passed for exported strategies (stage=phase2)"
        in capsys.readouterr().out
    )
    assert len(calls) == 4
    assert {stage for _, stage in calls} == {"phase2"}

    monkeypatch.setattr(
        "validate_candidate.validate_with_pipeline_schema",
        lambda **kw: ["schema says no"],
    )
    assert run_main(monkeypatch, *args, "--force-export") == 1
    stdout = capsys.readouterr().out
    assert "[ERROR] exported strategies failed pipeline validation:" in stdout
    assert "  - edge_auto_vcp_brk_20260220: schema says no" in stdout


def test_main_export_of_news_reaction_ticket_fails_contract(
    monkeypatch, capsys, ohlcv, tmp_path
) -> None:
    """Pinned: news_reaction tickets land in the exportable folder but the contract
    rejects them (no downstream detector), so --export-strategies-dir aborts with exit 1."""
    news = tmp_path / "news.csv"
    news.write_text("symbol,timestamp,reaction_1d\nBRK,2026-02-20,0.10\n", encoding="utf-8")
    strategies = tmp_path / "strategies"
    rc = run_main(
        monkeypatch,
        *base_args(ohlcv, tmp_path / "out"),
        "--news-reactions",
        str(news),
        "--export-strategies-dir",
        str(strategies),
    )
    stdout = capsys.readouterr().out
    assert rc == 1
    assert "[ERROR] export/validation integration failed" in stdout
    assert "news_reaction has no downstream detector" in stdout


# --- write_outputs --------------------------------------------------------------


def test_write_outputs_with_empty_inputs(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "out"
    exportable, research, report = adc.write_outputs(
        out, adc.date(2026, 2, 20), "Neutral", {"pct_above_ma50": 0.5}, [], [], [], [], []
    )
    assert exportable == [] and research == []
    assert report == out / "daily_report.md"
    assert (out / "watchlist.csv").read_text().strip() == (
        "symbol,entry_family,hypothesis_type,priority_score"
    )
    assert json.loads((out / "anomalies.json").read_text()) == []
    manifest = json.loads((out / "run_manifest.json").read_text())
    assert manifest["watchlist_count"] == 0
    assert manifest["output_dir"] == str(out)
    assert manifest["generated_at_utc"].endswith("+00:00")
    assert (out / "tickets" / "exportable").is_dir()
    assert (out / "tickets" / "research_only").is_dir()
