"""Real screening outputs must cross the checkpoint count/completion boundary."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build_discovery_pool as DISCOVERY
import manage_run_state as RUN_STATE
import screen_universe as SCREEN

ASSETS = SCRIPTS_DIR.parent / "assets"
AS_OF = "2026-08-22T14:00:00-07:00"


def _listing(symbol: str, *, eligible: bool) -> dict:
    pe = 16.0 if eligible else 80.0
    return {
        "symbol": symbol,
        "country": "US",
        "currency": "USD",
        "exchange": "NASDAQ",
        "sector": "Technology",
        "industry": "Software",
        "is_actively_trading": True,
        "is_common_stock": True,
        "price": 40.0,
        "market_cap": 3_500_000_000,
        "average_daily_dollar_volume": 12_000_000.0,
        "average_daily_dollar_volume_method": "provider_average_dollar_volume",
        "average_volume_period_days": 20,
        "liquidity_source_ids": ["fictional-listing"],
        "revenue_growth_pct": 14.0 if eligible else -5.0,
        "eps_growth_pct": 22.0 if eligible else -10.0,
        "standard_fcf": 250_000_000.0,
        "roic_pct": 18.0,
        "forward_pe": pe,
        "forward_eps": 40.0 / pe,
        "forward_pe_period": "FY1",
        "forward_fiscal_year": "FY2027",
        "forward_period_end": "2027-06-30",
        "forward_estimate_as_of": AS_OF,
        "forward_estimate_source_ids": ["fictional-estimate"],
        "forward_metric_origin": "computed_from_price_and_fy1_eps",
        "analyst_count": 6,
        "dilution_pct": 1.0,
        "net_debt_to_ebitda": 1.0,
        "fcf_yield_pct": 6.0,
    }


def _produce(
    root: Path, *, bounded=False, eligible=False, exhausted=True, selection_limit=None
) -> Path:
    """Run original production CLIs, including their artifact/hash writers."""
    listing = root / "listing.jsonl"
    listing.write_text(
        "".join(
            json.dumps(_listing(symbol, eligible=eligible)) + "\n" for symbol in ("AAA", "BBB")
        ),
        encoding="utf-8",
    )
    output = root / "screen"
    args = [
        "--input",
        str(listing),
        "--output-dir",
        str(output),
        "--analysis-as-of",
        AS_OF,
        "--source-id",
        "fictional-listing",
        "--retrieval-min-market-cap",
        "500000000",
        "--retrieval-max-market-cap",
        "20000000000",
        "--provider-reported-total",
        "2",
        "--pages-fetched",
        "1",
        "--pagination-exhausted",
    ]
    if bounded:
        assert (
            DISCOVERY.main(
                [
                    "--input",
                    str(listing),
                    "--output-dir",
                    str(output),
                    "--source-id",
                    "fictional-listing",
                    "--max-pool",
                    "1",
                ]
            )
            == 0
        )
        args += [
            "--candidate-pool",
            str(output / "discovery-pool.jsonl"),
            "--discovery-audit",
            str(output / "discovery-audit.json"),
            "--candidate-generation-mode",
            "liquidity_stratified_estimates",
        ]
    if exhausted:
        args.append("--candidate-pool-exhausted")
    if selection_limit is not None:
        args += ["--max-deep-dives", str(selection_limit)]
    assert SCREEN.main(args) in (0, 2)
    return output / "broad-screen-audit.json"


def _init(root: Path) -> Path:
    run = root / "checkpoint"
    assert (
        RUN_STATE.main(
            [
                "init",
                "--run-dir",
                str(run),
                "--analysis-as-of",
                AS_OF,
                "--price-as-of",
                AS_OF,
                "--session",
                "regular_close",
                "--price-source-id",
                "fictional-quote",
                "--market-context",
                str(ASSETS / "market-context.example.json"),
                "--global-sources",
                str(ASSETS / "global-sources.example.json"),
            ]
        )
        == 0
    )
    return run


def _attach(run: Path, audit: Path) -> int:
    return RUN_STATE.main(
        [
            "set-screening-audit",
            "--run-dir",
            str(run),
            "--audit",
            str(audit),
        ]
    )


@pytest.mark.parametrize("bounded", [False, True], ids=["full", "bounded"])
def test_zero_selection_producer_to_complete_snapshot(tmp_path, bounded):
    audit_path = _produce(tmp_path, bounded=bounded)
    audit = json.loads(audit_path.read_text())
    status = "no_qualifying_candidates" + ("_in_bounded_pool" if bounded else "")
    assert audit["candidate_pool_status"] == status
    assert audit["deep_dive_plan"]["selected_count"] == 0
    assert audit["selected_symbols"] == []
    assert audit["enrichment"]["candidate_pool_exhausted"] is True
    run = _init(tmp_path)
    assert _attach(run, audit_path) == 0
    assert RUN_STATE.main(["set-status", "--run-dir", str(run), "complete"]) == 0
    output = tmp_path / "final.json"
    assert RUN_STATE.main(["assemble", "--run-dir", str(run), "--output", str(output)]) == 0
    snapshot = json.loads(output.read_text())
    assert snapshot["run_metadata"]["status"] == "complete"
    assert snapshot["run_metadata"]["selected_symbols"] == []
    assert snapshot["candidates"] == []
    assert snapshot["screening_audit"]["candidate_pool_status"] == status
    assert snapshot["screening_audit"]["conclusion_scope"] == (
        "stratified_discovery_pool" if bounded else "full_listing_universe"
    )


@pytest.mark.parametrize(
    "count",
    [None, -1, True, False, 2.0, 2.9, float("nan"), float("inf"), "2", "bad", [2], {"value": 2}],
    ids=[
        "null",
        "negative",
        "true",
        "false",
        "float",
        "fractional",
        "nan",
        "infinity",
        "numeric-string",
        "text",
        "array",
        "object",
    ],
)
def test_invalid_count_fails_cleanly_without_changing_state(tmp_path, capsys, count):
    audit_path = _produce(tmp_path, eligible=True)
    audit = json.loads(audit_path.read_text())
    assert audit["deep_dive_plan"]["selected_count"] == 2
    audit["deep_dive_plan"]["selected_count"] = count
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    run = _init(tmp_path)
    before = (run / "run_state.json").read_bytes()
    capsys.readouterr()
    assert _attach(run, audit_path) == 1
    assert "deep_dive_plan.selected_count" in capsys.readouterr().err
    assert (run / "run_state.json").read_bytes() == before


@pytest.mark.parametrize("missing", [False, True], ids=["mismatched", "missing"])
def test_missing_or_inconsistent_count_is_rejected(tmp_path, missing):
    audit_path = _produce(tmp_path, eligible=True)
    audit = json.loads(audit_path.read_text())
    if missing:
        del audit["deep_dive_plan"]["selected_count"]
    else:
        audit["deep_dive_plan"]["selected_count"] = 1
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    run = _init(tmp_path)
    before = (run / "run_state.json").read_bytes()
    assert _attach(run, audit_path) == 1
    assert (run / "run_state.json").read_bytes() == before


@pytest.mark.parametrize("count", [False, True])
def test_boolean_count_is_rejected_even_when_numerically_equal(tmp_path, count):
    audit_path = _produce(tmp_path, eligible=count, selection_limit=1)
    audit = json.loads(audit_path.read_text())
    assert audit["deep_dive_plan"]["selected_count"] == int(count)
    audit["deep_dive_plan"]["selected_count"] = count
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    run = _init(tmp_path)
    assert _attach(run, audit_path) == 1


def test_positive_selection_still_requires_verified_candidates(tmp_path):
    audit_path = _produce(tmp_path, eligible=True)
    run = _init(tmp_path)
    assert _attach(run, audit_path) == 0
    state = json.loads((run / "run_state.json").read_text())
    assert state["unprocessed_candidates"] == ["AAA", "BBB"]
    assert RUN_STATE.main(["set-status", "--run-dir", str(run), "complete"]) == 1


def test_zero_count_does_not_authorize_unexhausted_pool_completion(tmp_path):
    audit_path = _produce(tmp_path, exhausted=False)
    audit = json.loads(audit_path.read_text())
    assert audit["candidate_pool_status"] == "insufficient_data"
    assert audit["deep_dive_plan"]["selected_count"] == 0
    run = _init(tmp_path)
    assert _attach(run, audit_path) == 0
    assert RUN_STATE.main(["set-status", "--run-dir", str(run), "complete"]) == 1
    assert (
        RUN_STATE.main(
            [
                "assemble",
                "--run-dir",
                str(run),
                "--output",
                str(tmp_path / "invalid.json"),
            ]
        )
        == 1
    )
    assert not (tmp_path / "invalid.json").exists()


@pytest.mark.parametrize("tamper", ["artifact", "commitment"])
def test_zero_count_keeps_artifact_and_commitment_guards(tmp_path, capsys, tamper):
    audit_path = _produce(tmp_path)
    audit = json.loads(audit_path.read_text())
    if tamper == "artifact":
        artifact = audit_path.parent / audit["candidate_pool"]["artifact_path"]
        artifact.write_bytes(artifact.read_bytes() + b" ")
        expected = "artifact SHA-256"
    else:
        audit["deep_dive_plan"]["selected_set_sha256"] = "0" * 64
        audit_path.write_text(json.dumps(audit), encoding="utf-8")
        expected = "selected_set_sha256"
    run = _init(tmp_path)
    before = (run / "run_state.json").read_bytes()
    capsys.readouterr()
    assert _attach(run, audit_path) == 1
    assert expected in capsys.readouterr().err
    assert (run / "run_state.json").read_bytes() == before


@pytest.mark.parametrize("bounded", [False, True], ids=["full", "bounded"])
def test_packaged_cli_completes_zero_candidate_run(tmp_path, bounded):
    audit = _produce(tmp_path, bounded=bounded)
    run = _init(tmp_path)
    destination = tmp_path / "unpacked"
    package = SCRIPTS_DIR.parents[2] / "skill-packages/us-undervalued-growth-screener.skill"
    with ZipFile(package) as archive:
        archive.extractall(destination)
    script = destination / "us-undervalued-growth-screener/scripts/manage_run_state.py"
    assert script.read_bytes() == (SCRIPTS_DIR / "manage_run_state.py").read_bytes()
    output = tmp_path / "packaged-final.json"
    commands = [
        ["set-screening-audit", "--run-dir", str(run), "--audit", str(audit)],
        ["set-status", "--run-dir", str(run), "complete"],
        ["assemble", "--run-dir", str(run), "--output", str(output)],
    ]
    for command in commands:
        result = subprocess.run(
            [sys.executable, str(script), *command],
            capture_output=True,
            text=True,
            check=False,
            cwd=tmp_path,
        )
        assert result.returncode == 0, result.stderr
    snapshot = json.loads(output.read_text())
    assert snapshot["run_metadata"]["status"] == "complete"
    assert snapshot["candidates"] == []
