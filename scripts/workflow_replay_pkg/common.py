"""Shared errors, loaders, CLI runner, and small validation helpers."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from .constants import DIGEST_ALLOWLIST_KEYS, RFC3339_PATTERN, SENSITIVE_ENV_MARKERS


class ReplayError(RuntimeError):
    """Fail-closed replay error with an auditable completed-step boundary."""

    def __init__(self, message: str, completed_steps: list[int] | None = None):
        super().__init__(message)
        self.completed_steps = list(completed_steps or [])


@dataclass(frozen=True)
class ExecutorRegistration:
    """An executor and its non-overridable evidence classification."""

    mode: str
    run: Callable[..., dict[str, dict[str, Any]]]
    components: tuple[str, ...] = ()


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ReplayError(f"cannot load YAML {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReplayError(f"YAML root must be a mapping: {path}")
    return payload


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayError(f"invalid {label} JSON at {path}: {exc}") from exc


def _dump_yaml_with_digest_allowlist(payload: Any) -> str:
    """Serialize fixture evidence while marking deterministic hashes as non-secrets."""
    rendered = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    keys = "|".join(sorted(re.escape(key) for key in DIGEST_ALLOWLIST_KEYS))
    digest_line = re.compile(
        rf"^(\s+(?:{keys}): [0-9a-f]{{64}})$",
        re.MULTILINE,
    )
    return digest_line.sub(r"\1  # pragma: allowlist secret", rendered)


def _schema_error_details(schema: Mapping[str, Any], payload: Any) -> list[str]:
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda error: list(error.path),
    )
    return [f"{'.'.join(map(str, error.path)) or '<root>'}: {error.message}" for error in errors]


def _require_rfc3339(value: Any, label: str) -> None:
    if not isinstance(value, str) or not RFC3339_PATTERN.fullmatch(value):
        raise ReplayError(f"{label} must be an RFC 3339 date-time with timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplayError(f"{label} must be a valid RFC 3339 date-time: {value!r}") from exc
    if parsed.utcoffset() is None:
        raise ReplayError(f"{label} must include an RFC 3339 timezone")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _scrubbed_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in SENSITIVE_ENV_MARKERS)
    }


def _run_cli(
    command: list[str],
    repo_root: Path,
    *,
    path_override: Path | None = None,
    env_overrides: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = _scrubbed_environment()
    # Native CLIs print Unicode status lines. On Windows a pipe otherwise uses
    # the legacy code page, which cannot encode them, so pin stdio to UTF-8.
    environment["PYTHONIOENCODING"] = "utf-8"
    if path_override is not None:
        environment["PATH"] = str(path_override)
    if env_overrides:
        for key in env_overrides:
            if any(marker in key.upper() for marker in SENSITIVE_ENV_MARKERS):
                raise ReplayError(f"env_overrides must not set a sensitive variable: {key}")
        environment.update(env_overrides)
    completed = subprocess.run(
        command,
        cwd=repo_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no CLI output"
        raise ReplayError(f"native CLI failed ({completed.returncode}): {detail}")
    return completed


def _repo_module(repo_root: Path, module_name: str, scripts_dir: Path) -> Any:
    """Import one repository script module without invoking the uv launcher."""
    scripts_text = str(scripts_dir.resolve())
    if scripts_text not in sys.path:
        sys.path.insert(0, scripts_text)
    importlib.invalidate_caches()
    module = importlib.import_module(module_name)
    module_path = Path(module.__file__).resolve()
    if scripts_dir.resolve() not in module_path.parents:
        raise ReplayError(
            f"refusing unexpected {module_name} import outside repository skill: {module_path}"
        )
    return module


def _trader_memory_modules(repo_root: Path) -> tuple[Any, Any]:
    scripts_dir = repo_root / "skills" / "trader-memory-core" / "scripts"
    store = _repo_module(repo_root, "thesis_store", scripts_dir)
    review = _repo_module(repo_root, "thesis_review", scripts_dir)
    return store, review


def _write_yaml(path: Path, payload: Any, *, digest_allowlist: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if digest_allowlist:
        text = _dump_yaml_with_digest_allowlist(payload)
    else:
        text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _require_mapping_keys(
    payload: Any,
    *,
    label: str,
    required: set[str],
    optional: set[str] | None = None,
) -> Mapping[str, Any]:
    if not isinstance(payload, dict):
        raise ReplayError(f"{label} must be a mapping")
    missing = required - set(payload)
    unexpected = set(payload) - required - set(optional or set())
    if missing or unexpected:
        raise ReplayError(
            f"invalid {label} keys: missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )
    return payload


def _require_non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReplayError(f"{label} must be a non-empty string")
    return value


def _require_finite_number(
    value: Any,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    integer: bool = False,
) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReplayError(f"{label} must be {'an integer' if integer else 'numeric'}")
    if integer and not isinstance(value, int):
        raise ReplayError(f"{label} must be an integer")
    if not math.isfinite(value):
        raise ReplayError(f"{label} must be finite")
    if minimum is not None and value < minimum:
        raise ReplayError(f"{label} must be >= {minimum:g}")
    if maximum is not None and value > maximum:
        raise ReplayError(f"{label} must be <= {maximum:g}")
    return value


def _load_module_from_path(path: Path, label: str) -> Any:
    """Load same-named skill modules under a path-derived collision-free name."""
    path = path.resolve()
    if not path.is_file():
        raise ReplayError(f"missing native module for {label}: {path}")
    digest = hashlib.sha256(str(path).encode()).hexdigest()[:16]
    module_name = f"_workflow_replay_{re.sub(r'[^a-z0-9]+', '_', label.lower())}_{digest}"
    module_spec = importlib.util.spec_from_file_location(module_name, path)
    if module_spec is None or module_spec.loader is None:
        raise ReplayError(f"cannot load native module for {label}: {path}")
    module = importlib.util.module_from_spec(module_spec)
    # dataclasses and postponed annotation resolution consult sys.modules while
    # the module body is executing. Register the collision-free name first.
    sys.modules[module_name] = module
    try:
        module_spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise ReplayError(f"cannot initialize native module for {label}: {exc}") from exc
    return module


def _assert_finite_json(value: Any, label: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _assert_finite_json(child, f"{label}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_finite_json(child, f"{label}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ReplayError(f"{label} must be finite")


def _parse_rfc3339(value: Any, label: str) -> datetime:
    _require_rfc3339(value, label)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
