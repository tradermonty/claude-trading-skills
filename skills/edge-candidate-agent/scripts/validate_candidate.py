#!/usr/bin/env python3
"""Validate candidate strategy artifacts against interface and pipeline rules."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from candidate_contract import read_yaml, validate_interface_contract


def validate_with_pipeline_schema(
    strategy_path: Path,
    pipeline_root: Path,
    stage: str,
) -> list[str]:
    """Validate with trade-strategy-pipeline source tree and stage rules."""
    src_dir = pipeline_root / "src"
    if not src_dir.exists():
        return [f"pipeline source directory not found: {src_dir}"]
    return validate_with_pipeline_uv(
        strategy_path=strategy_path,
        pipeline_root=pipeline_root,
        stage=stage,
    )


def validate_with_pipeline_uv(
    strategy_path: Path,
    pipeline_root: Path,
    stage: str,
) -> list[str]:
    """Validate by executing inside pipeline's `uv run` environment."""
    snippet = "\n".join(
        [
            "import json",
            "from pathlib import Path",
            "import yaml",
            "from pipeline.spec.schema import StrategySpec",
            "from pipeline.spec.validator import validate_spec",
            f"strategy_path = Path({strategy_path.as_posix()!r})",
            f"stage = {stage!r}",
            "with open(strategy_path) as f:",
            "    payload = yaml.safe_load(f)",
            "spec = StrategySpec(**payload)",
            "errors = validate_spec(spec, stage=stage)",
            "print(json.dumps({'errors': errors}))",
        ]
    )

    result = subprocess.run(
        ["uv", "run", "python", "-c", snippet],
        cwd=str(pipeline_root),
        env=_uv_env(),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return [f"uv pipeline validation failed: {detail}"]

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return ["uv pipeline validation produced no output"]

    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        return [f"failed to parse uv validation output as JSON: {exc}"]

    errors = payload.get("errors", [])
    if not isinstance(errors, list):
        return ["uv validation output missing 'errors' list"]
    return [str(error) for error in errors]


def _uv_env() -> dict[str, str]:
    """Return subprocess environment with writable uv cache."""
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/tmp/uv-cache-edge-candidate-agent")
    return env


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate strategy candidate against edge-finder interface and pipeline constraints.",
    )
    parser.add_argument("--strategy", required=True, help="Path to strategy.yaml")
    parser.add_argument(
        "--candidate-id",
        default=None,
        help="Candidate id override (defaults to strategy parent directory name)",
    )
    parser.add_argument(
        "--stage", default="phase1", help="Pipeline validation stage (default: phase1)"
    )
    parser.add_argument(
        "--pipeline-root",
        default=None,
        help="Path to trade-strategy-pipeline repository root for strict schema validation",
    )
    parser.add_argument(
        "--strict-pipeline",
        action="store_true",
        help="Fail when --pipeline-root is not provided",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    strategy_path = Path(args.strategy).resolve()
    if not strategy_path.exists():
        print(f"[ERROR] strategy not found: {strategy_path}")
        return 1

    try:
        strategy_payload = read_yaml(strategy_path)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] failed to read strategy YAML: {exc}")
        return 1

    candidate_id = args.candidate_id or strategy_path.parent.name
    errors = validate_interface_contract(
        strategy_payload,
        candidate_id=candidate_id,
        stage=args.stage,
    )

    pipeline_errors: list[str] = []
    if args.pipeline_root:
        pipeline_root = Path(args.pipeline_root).resolve()
        pipeline_errors = validate_with_pipeline_schema(
            strategy_path=strategy_path,
            pipeline_root=pipeline_root,
            stage=args.stage,
        )
    elif args.strict_pipeline:
        pipeline_errors = ["--strict-pipeline requires --pipeline-root"]

    all_errors = errors + pipeline_errors
    if all_errors:
        print("[ERROR] Candidate validation failed:")
        for error in all_errors:
            print(f"  - {error}")
        return 1

    print(f"[OK] Candidate validation passed: {strategy_path}")
    print(f"[OK] candidate_id={candidate_id}")
    if args.pipeline_root:
        print(f"[OK] pipeline schema validated against stage={args.stage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
