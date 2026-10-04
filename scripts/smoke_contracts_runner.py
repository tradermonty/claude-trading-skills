#!/usr/bin/env python3
"""Nightly clean-room smoke runner for per-skill smoke contracts (issue #349).

Consumes the declarative SMOKE_CONTRACTS table from check_skill_deps.py and
executes, per third-party-required executable skill:

1. a fresh venv installing ONLY the declared requirements, plus
2. a reverse-import probe for every required distribution, plus
3. each recorded contract command (args, expected exit, expected output
   substrings), or records a pending/skip row when no contract exists yet.

Writes machine-readable evidence JSON and exits nonzero when any row fails —
the nightly is promoted to fail-closed (checklist item 4) only together with
this exit-code fix; flipping `continue-on-error` alone does nothing.

PRs do NOT run this file: the PR path stays network-free via
``check_skill_deps.py check`` and the golden ``smoke`` subcommand in ci.yml.
"""

from __future__ import annotations

import argparse
import json
import subprocess  # runner-only; check_skill_deps.py must never import this
import sys
import venv
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

import check_skill_deps as deps  # noqa: E402

REPO_ROOT = deps.ROOT


def create_venv(path: Path) -> Path:
    """Isolated behind a module function for unit-test substitution."""
    venv.create(path, with_pip=True)
    return path


def run_command(cmd: list[str], timeout: int = 120) -> tuple[int, str]:
    """Isolated behind a module function for unit-test substitution."""
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout + proc.stderr


def _contract_rows(python: Path, skill_id: str, root: Path) -> tuple[list[dict], list[str]]:
    contracts = deps.SMOKE_CONTRACTS.get(skill_id) or []
    if not contracts and skill_id in deps.PENDING_SMOKE_CONTRACTS:
        return [{"contracts_status": "pending_wave2"}], []
    rows: list[dict] = []
    errors: list[str] = []
    for contract in contracts:
        if contract.skip_reason:
            rows.append({"script": "", "skipped": True, "skip_reason": contract.skip_reason})
            continue
        cmd = [str(python), str(root / contract.script), *contract.args]
        code, out = run_command(cmd)
        matched = all(token in out for token in contract.expect_out)
        row = {
            "script": contract.script,
            "args": list(contract.args),
            "expect_exit": contract.expect_exit,
            "expect_exit_match": code == contract.expect_exit,
            "expect_out_match": matched,
            "skipped": False,
        }
        if contract.fixture:
            row["fixture"] = contract.fixture
            row["fixture_present"] = (root / contract.fixture).is_file()
        rows.append(row)
        if code != contract.expect_exit:
            errors.append(f"{contract.script}: expect_exit {contract.expect_exit} got {code}")
        if not matched:
            errors.append(f"{contract.script}: missing expected output {contract.expect_out!r}")
        if contract.fixture and row["fixture_present"] is False:
            errors.append(f"{contract.script}: fixture missing: {contract.fixture}")
    return rows, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="deps-nightly-smoke.json")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    root = args.root or REPO_ROOT

    reverse = {}
    for top, dist in deps.IMPORT_TO_DIST.items():
        reverse.setdefault(dist.lower(), top)

    results = []
    for manifest in sorted((root / "skills").glob("*/requirements.txt")):
        skill_id = manifest.parent.name
        entries, errors = deps.parse_requirements(manifest)
        required = [e for e in entries.values() if not e.optional]
        if errors or not required:
            continue  # parse errors gate in ci.yml; stdlib-only needs no venv
        venv_dir = root / f".venv-smoke-{skill_id}"
        row = {
            "id": skill_id,
            "ok": True,
            "errors": [],
            "contracts_status": "executed",
        }
        try:
            python = create_venv(venv_dir) / "bin" / "python"
            code, out = run_command(
                [str(python), "-m", "pip", "install", "-q", "-r", str(manifest)],
                timeout=600,
            )
            if code != 0:
                raise RuntimeError(f"pip install failed: {out.strip()[:400]}")
            for entry in required:
                top = reverse.get(entry.dist.lower(), entry.dist)
                code, out = run_command([str(python), "-c", f"import {top}"])
                if code != 0:
                    row["ok"] = False
                    row["errors"].append(f"cannot import {top}: {out.strip()[-400:]}")
            contract_rows, contract_errors = _contract_rows(python, skill_id, root)
            if contract_errors:
                row["ok"] = False
                row["errors"].extend(contract_errors)
            row["contracts"] = contract_rows
            if contract_rows == [{"contracts_status": "pending_wave2"}]:
                row["contracts_status"] = "pending_wave2"
                row["contracts"] = []
        except Exception as exc:  # noqa: BLE001 - evidence harness must record
            row["ok"] = False
            row["errors"].append(f"harness error: {exc}")
        results.append(row)
        print(("OK " if row["ok"] else "FAIL ") + skill_id + _status_suffix(row))

    evidence = {"skills": results}
    Path(args.output).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    failed = [row["id"] for row in results if not row["ok"]]
    if failed:
        print(f"clean-room failures: {', '.join(failed)}")
        return 1
    print("all clean-room smoke rows ok")
    return 0


def _status_suffix(row: dict) -> str:
    if row.get("contracts_status") == "pending_wave2":
        return " (contracts pending wave2)"
    return ""
