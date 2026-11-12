"""Artifact discovery, file validation, and provenance checks."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from validate_provenance import validate_provenance

from .common import ReplayError
from .normalize import _file_sha256


def _latest_report(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if len(matches) != 1:
        raise ReplayError(
            f"expected exactly one report matching {pattern!r} in {directory}, got {len(matches)}"
        )
    return matches[0]


def _artifact_paths(
    stage: Path, output_files: Mapping[str, Mapping[str, str]]
) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for artifact_id, roles in output_files.items():
        artifacts[artifact_id] = {
            "files": {role: str((stage / filename).resolve()) for role, filename in roles.items()}
        }
    return artifacts


def _validate_artifact_files(
    stage: Path,
    artifacts: Mapping[str, dict[str, Any]],
    label: str,
) -> None:
    stage_root = stage.resolve()
    seen: dict[Path, str] = {}
    for artifact_id, bundle in artifacts.items():
        files = bundle.get("files") if isinstance(bundle, dict) else None
        if not isinstance(files, dict) or not files:
            raise ReplayError(f"{label} artifact {artifact_id!r} has no declared files")
        for role, raw_path in files.items():
            path = Path(raw_path).resolve()
            try:
                path.relative_to(stage_root)
            except ValueError as exc:
                raise ReplayError(
                    f"{label} artifact {artifact_id}.{role} escapes staging: {path}"
                ) from exc
            if not path.is_file():
                raise ReplayError(
                    f"{label} artifact {artifact_id}.{role} is a missing staged file: {path}"
                )
            previous = seen.get(path)
            if previous:
                raise ReplayError(
                    f"{label} has duplicate staged file {path.name!r}: "
                    f"{previous} and {artifact_id}.{role}"
                )
            seen[path] = f"{artifact_id}.{role}"


def _validate_artifact_provenance(
    artifacts: Mapping[str, dict[str, Any]],
    required: Mapping[str, int],
    label: str,
) -> None:
    """Validate canonical provenance; declarations survive mutable artifact bundles."""
    for artifact_id, bundle in artifacts.items():
        producer = required.get(artifact_id)
        context = f"{label} artifact {artifact_id!r}"
        if producer is not None:
            context += f" (provenance required by producer step {producer})"
        canonical = bundle["files"].get("canonical")
        if not canonical:
            if producer is not None:
                raise ReplayError(f"{context}: missing canonical role for data_provenance")
            continue
        path = Path(canonical)
        suffix = path.suffix.lower()
        if suffix not in {".json", ".yaml", ".yml"}:
            if producer is not None:
                raise ReplayError(f"{context}: data_provenance requires canonical JSON/YAML")
            continue
        try:
            text = path.read_text(encoding="utf-8")
            payload = json.loads(text) if suffix == ".json" else yaml.safe_load(text)
        except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
            raise ReplayError(
                f"{context}: cannot parse canonical provenance payload: {exc}"
            ) from exc
        has_block = isinstance(payload, dict) and "data_provenance" in payload
        if not has_block:
            if producer is not None:
                raise ReplayError(f"{context}: missing data_provenance object")
            continue
        errors = validate_provenance(payload["data_provenance"])
        if errors:
            raise ReplayError(f"{context}: invalid data_provenance:\n- " + "\n- ".join(errors))


def _artifact_file_digests(
    artifacts: Mapping[str, dict[str, Any]],
) -> dict[str, str]:
    """Seal every declared artifact file by its stable artifact-role identity."""
    digests: dict[str, str] = {}
    for artifact_id, bundle in artifacts.items():
        for role, raw_path in bundle["files"].items():
            digests[f"{artifact_id}.{role}"] = _file_sha256(Path(raw_path))
    return digests
