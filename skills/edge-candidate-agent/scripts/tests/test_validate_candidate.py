"""Unit tests for validate_candidate.py."""

import subprocess
import sys
from pathlib import Path

import validate_candidate
import yaml


def build_valid_strategy(strategy_id: str) -> dict:
    return {
        "id": strategy_id,
        "name": "Validation Test Strategy",
        "description": "test",
        "universe": {
            "type": "us_equities",
            "index": "sp500",
            "filters": ["avg_volume > 500_000", "price > 10"],
        },
        "signals": {
            "entry": {
                "type": "pivot_breakout",
                "conditions": ["vcp_pattern_detected"],
                "trend_filter": ["price > sma_200"],
            },
            "exit": {
                "stop_loss": "7% below entry",
                "trailing_stop": "below 21-day EMA",
                "take_profit": "risk_reward_3x",
            },
        },
        "risk": {
            "risk_per_trade": 0.01,
            "max_positions": 5,
            "max_sector_exposure": 0.30,
        },
        "cost_model": {
            "commission_per_share": 0.0,
            "slippage_bps": 5,
        },
        "validation": {"method": "full_sample"},
        "promotion_gates": {
            "min_trades": 200,
            "max_drawdown": 0.15,
            "sharpe": 1.0,
            "profit_factor": 1.2,
        },
        "vcp_detection": {"min_contractions": 2, "contraction_ratio": 0.75},
    }


def write_strategy(path: Path, strategy_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_valid_strategy(strategy_id)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False))


def test_validate_with_pipeline_schema_requires_src_dir(tmp_path: Path) -> None:
    strategy_path = tmp_path / "strategy.yaml"
    write_strategy(strategy_path, "edge_schema_missing_src_v1")
    errors = validate_candidate.validate_with_pipeline_schema(
        strategy_path=strategy_path,
        pipeline_root=tmp_path,
        stage="phase1",
    )
    assert any("pipeline source directory not found" in error for error in errors)


def test_validate_with_pipeline_schema_delegates_to_uv(
    tmp_path: Path,
    monkeypatch,
) -> None:
    strategy_path = tmp_path / "strategy.yaml"
    write_strategy(strategy_path, "edge_schema_delegate_v1")
    (tmp_path / "src").mkdir()

    calls = {}

    def fake_validate_with_pipeline_uv(
        strategy_path: Path, pipeline_root: Path, stage: str
    ) -> list[str]:
        calls["strategy_path"] = strategy_path
        calls["pipeline_root"] = pipeline_root
        calls["stage"] = stage
        return []

    monkeypatch.setattr(
        validate_candidate, "validate_with_pipeline_uv", fake_validate_with_pipeline_uv
    )
    errors = validate_candidate.validate_with_pipeline_schema(
        strategy_path=strategy_path,
        pipeline_root=tmp_path,
        stage="phase1",
    )

    assert errors == []
    assert calls["strategy_path"] == strategy_path
    assert calls["pipeline_root"] == tmp_path
    assert calls["stage"] == "phase1"


def test_validate_with_pipeline_uv_handles_subprocess_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    strategy_path = tmp_path / "strategy.yaml"
    write_strategy(strategy_path, "edge_uv_fail_v1")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(validate_candidate.subprocess, "run", fake_run)
    errors = validate_candidate.validate_with_pipeline_uv(
        strategy_path=strategy_path,
        pipeline_root=tmp_path,
        stage="phase1",
    )
    assert any("uv pipeline validation failed" in error for error in errors)


def test_validate_with_pipeline_uv_parses_error_list(
    tmp_path: Path,
    monkeypatch,
) -> None:
    strategy_path = tmp_path / "strategy.yaml"
    write_strategy(strategy_path, "edge_uv_json_v1")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout='{"errors":["phase1 violation"]}\n',
            stderr="",
        )

    monkeypatch.setattr(validate_candidate.subprocess, "run", fake_run)
    errors = validate_candidate.validate_with_pipeline_uv(
        strategy_path=strategy_path,
        pipeline_root=tmp_path,
        stage="phase1",
    )
    assert errors == ["phase1 violation"]


def test_validate_with_pipeline_uv_rejects_invalid_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    strategy_path = tmp_path / "strategy.yaml"
    write_strategy(strategy_path, "edge_uv_bad_json_v1")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="not-json\n",
            stderr="",
        )

    monkeypatch.setattr(validate_candidate.subprocess, "run", fake_run)
    errors = validate_candidate.validate_with_pipeline_uv(
        strategy_path=strategy_path,
        pipeline_root=tmp_path,
        stage="phase1",
    )
    assert any("failed to parse uv validation output as JSON" in error for error in errors)


def test_main_returns_error_for_missing_strategy(monkeypatch, capsys, tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.yaml"
    monkeypatch.setattr(sys, "argv", ["validate_candidate.py", "--strategy", str(missing_path)])
    rc = validate_candidate.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "strategy not found" in out


def test_main_interface_only_success(monkeypatch, capsys, tmp_path: Path) -> None:
    strategy_id = "edge_main_success_v1"
    strategy_path = tmp_path / strategy_id / "strategy.yaml"
    write_strategy(strategy_path, strategy_id)

    monkeypatch.setattr(sys, "argv", ["validate_candidate.py", "--strategy", str(strategy_path)])
    rc = validate_candidate.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "Candidate validation passed" in out


def test_main_strict_pipeline_requires_root(monkeypatch, capsys, tmp_path: Path) -> None:
    strategy_id = "edge_main_strict_v1"
    strategy_path = tmp_path / strategy_id / "strategy.yaml"
    write_strategy(strategy_path, strategy_id)

    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_candidate.py", "--strategy", str(strategy_path), "--strict-pipeline"],
    )
    rc = validate_candidate.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "--strict-pipeline requires --pipeline-root" in out


def test_main_pipeline_root_uses_schema_validator(monkeypatch, capsys, tmp_path: Path) -> None:
    strategy_id = "edge_main_pipeline_v1"
    strategy_path = tmp_path / strategy_id / "strategy.yaml"
    write_strategy(strategy_path, strategy_id)

    def fake_validate_with_pipeline_schema(
        strategy_path: Path, pipeline_root: Path, stage: str
    ) -> list[str]:
        assert stage == "phase1"
        return ["forced pipeline error"]

    monkeypatch.setattr(
        validate_candidate,
        "validate_with_pipeline_schema",
        fake_validate_with_pipeline_schema,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_candidate.py",
            "--strategy",
            str(strategy_path),
            "--pipeline-root",
            str(tmp_path),
            "--stage",
            "phase1",
        ],
    )
    rc = validate_candidate.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "forced pipeline error" in out
