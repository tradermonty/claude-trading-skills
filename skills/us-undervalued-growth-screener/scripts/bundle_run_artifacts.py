#!/usr/bin/env python3
"""Create a deterministic, self-contained audit ZIP for a completed screen."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

try:
    from prepublish_audit import AuditError, _read_json, audit_publication
    from skill_version import runtime_metadata
except ModuleNotFoundError:
    import importlib.util

    def _load(name: str):
        path = Path(__file__).with_name(name + ".py")
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load {name}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    _audit = _load("prepublish_audit")
    _version = _load("skill_version")
    AuditError = _audit.AuditError
    _read_json = _audit._read_json
    audit_publication = _audit.audit_publication
    runtime_metadata = _version.runtime_metadata

FIXED_DATE = (2026, 1, 1, 0, 0, 0)
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".git"}
SECRET_TERMS = {".env", "credentials", "api_key", "apikey", "access_token", "secret"}


def _include(path: Path, run_dir: Path) -> bool:
    rel = path.relative_to(run_dir)
    if any(part in EXCLUDED_PARTS for part in rel.parts):
        return False
    lower = rel.as_posix().lower()
    if any(term in lower for term in SECRET_TERMS):
        raise ValueError(f"refusing to bundle possible secret file: {rel}")
    return path.is_file() and not path.name.endswith((".tmp", ".pyc"))


def _zip_info(name: str, mode: int = 0o644) -> ZipInfo:
    info = ZipInfo(name, FIXED_DATE)
    info.compress_type = ZIP_DEFLATED
    info.external_attr = mode << 16
    return info


def build_bundle(run_dir: Path, report_json: Path, report_md: Path, output: Path) -> dict:
    run_dir = run_dir.resolve()
    report = _read_json(report_json)
    markdown = report_md.read_text(encoding="utf-8")
    audit = audit_publication(report, report_markdown=markdown, artifact_root=run_dir)
    if not audit["valid"]:
        raise AuditError("prepublication audit failed: " + "; ".join(audit["errors"]))

    files = sorted(
        [path for path in run_dir.rglob("*") if _include(path, run_dir)],
        key=lambda path: path.relative_to(run_dir).as_posix(),
    )
    manifest = {
        "runtime": runtime_metadata(),
        "run_dir_name": run_dir.name,
        "files": [
            {
                "path": path.relative_to(run_dir).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size,
            }
            for path in files
        ],
        "prepublication_audit": audit,
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    try:
        with ZipFile(temp, "w") as archive:
            for path in files:
                rel = path.relative_to(run_dir).as_posix()
                mode = path.stat().st_mode & 0o777
                archive.writestr(_zip_info(rel, mode), path.read_bytes())
            archive.writestr(_zip_info("BUNDLE_MANIFEST.json"), manifest_bytes)
        os.replace(temp, output)
    finally:
        if temp.exists():
            temp.unlink()
    return {
        "runtime": runtime_metadata(),
        "output": str(output),
        "file_count": len(files),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    parser.add_argument("--report-md", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if "--version" in raw_argv:
        print(json.dumps(runtime_metadata(), sort_keys=True))
        return 0
    args = parse_args(raw_argv)
    if args.version:
        print(json.dumps(runtime_metadata(), sort_keys=True))
        return 0
    try:
        result = build_bundle(args.run_dir, args.report_json, args.report_md, args.output)
    except (AuditError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
