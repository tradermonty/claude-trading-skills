"""Path canonicalization, payload digests, and output normalization."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .common import ReplayError, _load_json, _write_json
from .constants import TIMESTAMP_FIELDS


def _safe_relative(base: Path, value: str, label: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ReplayError(f"{label} must be a safe relative path: {value!r}")
    resolved = (base / relative).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError as exc:
        raise ReplayError(f"{label} escapes {base}: {value!r}") from exc
    return resolved


def _paths_overlap(left: Path, right: Path) -> bool:
    """Return whether two resolved paths are equal or one contains the other."""
    left = left.resolve()
    right = right.resolve()
    return left == right or left in right.parents or right in left.parents


def _canonicalize(value: Any, fixed_timestamp: str, replacements: Mapping[str, str]) -> Any:
    path_replacements = {}
    resolved_replacements = {}
    literal_replacements = {}
    for source, replacement in replacements.items():
        path = Path(source)
        if not path.is_absolute():
            literal_replacements[source] = replacement
            continue
        resolved = str(path.resolve())
        # Path drops the trailing separator, but directory-prefix substitutions
        # need it to preserve relative output and avoid matching sibling names.
        if source.endswith((os.sep, os.altsep) if os.altsep else (os.sep,)):
            resolved = resolved.rstrip(os.sep) + source[-1]
        if resolved in resolved_replacements:
            previous = resolved_replacements[resolved]
            if previous != replacement:
                raise ReplayError(
                    f"conflicting path replacement for {resolved}: {previous} vs {replacement}"
                )
        resolved_replacements[resolved] = replacement
        # Keep both lexical and resolved spellings: output may contain either.
        path_replacements[source] = replacement
        path_replacements.setdefault(resolved, replacement)

    # The lexical /tmp prefix can also occur inside its resolved /private/tmp
    # spelling. Replace the longer spelling first, as well as specific files
    # before their parent directory. Ordinary literal replacements retain order.
    ordered_replacements = sorted(path_replacements.items(), key=lambda item: -len(item[0]))
    ordered_replacements.extend(literal_replacements.items())
    return _canonicalize_values(value, fixed_timestamp, ordered_replacements)


def _canonicalize_values(
    value: Any, fixed_timestamp: str, replacements: list[tuple[str, str]]
) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, child in value.items():
            if key in TIMESTAMP_FIELDS:
                normalized[key] = fixed_timestamp
            else:
                normalized[key] = _canonicalize_values(child, fixed_timestamp, replacements)
        return normalized
    if isinstance(value, list):
        return [_canonicalize_values(item, fixed_timestamp, replacements) for item in value]
    if isinstance(value, str):
        result = value
        for source, replacement in replacements:
            result = result.replace(source, replacement)
        return result
    return value


def _normalize_json_file(
    source: Path,
    destination: Path,
    fixed_timestamp: str,
    replacements: Mapping[str, str],
) -> None:
    payload = _load_json(source, source.name)
    _write_json(destination, _canonicalize(payload, fixed_timestamp, replacements))


def _normalize_jsonl_file(
    source: Path,
    destination: Path,
    fixed_timestamp: str,
    replacements: Mapping[str, str],
) -> None:
    records = []
    try:
        for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ReplayError(
                    f"invalid staged model book JSONL at line {line_number}: {exc}"
                ) from exc
    except OSError as exc:
        raise ReplayError(f"cannot read staged model book {source}: {exc}") from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(
        json.dumps(
            _canonicalize(record, fixed_timestamp, replacements),
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
        for record in records
    )
    destination.write_text(text, encoding="utf-8", newline="\n")


def _canonical_json_bytes(
    payload: Any,
    fixed_timestamp: str,
    replacements: Mapping[str, str] | None = None,
) -> bytes:
    canonical = _canonicalize(payload, fixed_timestamp, replacements or {})
    return (json.dumps(canonical, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode()


def _payload_sha256(
    payload: Any,
    fixed_timestamp: str,
    replacements: Mapping[str, str] | None = None,
) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload, fixed_timestamp, replacements)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


_ELAPSED_RE = re.compile(r" in \d+\.\d+s\b")


def _normalize_elapsed(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _normalize_elapsed(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_elapsed(v) for v in obj]
    if isinstance(obj, str):
        return _ELAPSED_RE.sub(" in <elapsed>s", obj)
    return obj


def _normalize_review_test_command(report: dict[str, Any]) -> None:
    """Replace the environment-specific pytest launcher with a replay token."""
    auto_review = report.get("auto_review")
    if not isinstance(auto_review, dict):
        raise ReplayError("skill review auto_review must be a mapping")

    status = auto_review.get("test_status")
    command = auto_review.get("test_command")
    command_statuses = {"passed", "failed", "timeout"}
    no_command_statuses = {"not_found", "tool_missing", "not_applicable", "skipped"}
    if status in no_command_statuses:
        if command is not None:
            raise ReplayError(f"skill review test_status {status!r} requires test_command: null")
        return
    if status not in command_statuses:
        raise ReplayError(f"unexpected skill review test_status: {status!r}")
    if not isinstance(command, str) or not command.strip():
        raise ReplayError(f"skill review test_status {status!r} requires a test command")

    prefixes = (
        "uv run --extra dev pytest ",
        f"{sys.executable} -m pytest ",
    )
    prefix = next((candidate for candidate in prefixes if command.startswith(candidate)), None)
    if prefix is None:
        raise ReplayError(f"unexpected skill review test command: {command!r}")

    # Keep every pytest argument byte-for-byte; only the launcher is replay metadata.
    pytest_arguments = command[len(prefix) :]
    if not pytest_arguments.strip():
        raise ReplayError("skill review test command requires pytest arguments")
    shell_markers = ("\n", "\r", "&&", "||", ";", "|", "&", ">", "<", "`", "$(")
    if any(marker in pytest_arguments for marker in shell_markers):
        raise ReplayError("skill review test command contains shell control syntax")
    auto_review["test_command"] = f"pytest {pytest_arguments}"


_PYTEST_WARNINGS_HEADER_RE = re.compile(r"^=+\s*warnings summary\s*=+$")


_PYTEST_DOCS_RE = re.compile(r"^-- Docs: https://docs\.pytest\.org/")


_PYTEST_WARNINGS_COUNT_RE = re.compile(r", \d+ warnings?(?= in \d+\.\d+s\b)")


_PYTEST_WARNING_ENTRY_RE = re.compile(
    r"^\s*(?:\S+\.py:\d+:\s*)?(?P<category>[A-Za-z_][\w.]*): (?P<message>.*)$"
)


_PYTEST_STATUS_LINE_RE = re.compile(
    r"^(?:\d+ (?:passed|failed|error|errors|skipped|deselected|xfailed|xpassed"
    r"|subtests? (?:passed|failed|skipped))|no tests ran)"
)


_PYTEST_LOCATION_LINE_RE = re.compile(r"^\S+\.py:\d+\s*$")


# Unbannered (layout B) entry: pytest 9 emits GC-time rm_rf warnings after the
# results line, without a ``warnings summary`` header or a ``-- Docs:`` footer.
_RM_RF_ENTRY_RE = re.compile(r".*_pytest/pathlib\.py:\d+: PytestWarning: \(rm_rf\) error removing ")


_RM_RF_OS_ERROR_RE = re.compile(r"<class 'OSError'>: \[Errno \d+\] Directory not empty: '")


_RM_RF_WARN_CALL_RE = re.compile(r"^\s*warnings\.warn\($")


def _remove_status_line_warnings_count(lines: list[str]) -> list[str]:
    """Remove the ``, N warnings`` fragment from the terminal status line only."""
    for index in range(len(lines) - 1, -1, -1):
        if _PYTEST_STATUS_LINE_RE.match(lines[index].strip()):
            result = list(lines)
            result[index] = _PYTEST_WARNINGS_COUNT_RE.sub("", result[index])
            return result
    return lines


def _is_warning_structural_line(line: str) -> bool:
    """True for the non-entry scaffolding lines pytest emits around warnings."""
    return (
        line.strip() == ""
        or _PYTEST_WARNINGS_HEADER_RE.match(line) is not None
        or _PYTEST_DOCS_RE.match(line) is not None
        or _PYTEST_LOCATION_LINE_RE.match(line) is not None
        or _RM_RF_OS_ERROR_RE.search(line) is not None
        or _RM_RF_WARN_CALL_RE.match(line) is not None
    )


def _is_rm_rf_warnings_noise(block: str) -> bool:
    """True when every summary entry is the known pytest temp-GC noise.

    The entry category is any identifier/dotted name, so a genuine custom
    warning class (e.g. ``DataQualityAlert``) is detected even though it does not
    end in ``Warning`` — otherwise the noise check would wrongly pass and the
    whole block (genuine warning included) would be deleted. Any line that is
    neither a parsed entry nor recognized scaffolding fails closed (block kept),
    so an unrecognized evidence line can never be silently removed.
    """
    entries = []
    for line in block.split("\n"):
        match = _PYTEST_WARNING_ENTRY_RE.match(line)
        if match is not None:
            entries.append(match)
            continue
        if not _is_warning_structural_line(line):
            return False
    if not entries:
        return False
    for match in entries:
        if match.group("category").rsplit(".", 1)[-1] != "PytestWarning":
            return False
        if "(rm_rf) error removing" not in match.group("message"):
            return False
    return True


def _strip_banner_framed_rm_rf(text: str) -> str:
    """Strip a ``warnings summary`` ... ``-- Docs:`` block that is all rm_rf noise."""
    lines = text.split("\n")
    header_index = next(
        (index for index, line in enumerate(lines) if _PYTEST_WARNINGS_HEADER_RE.match(line)),
        None,
    )
    if header_index is None:
        return text
    docs_index = next(
        (
            index
            for index in range(header_index + 1, len(lines))
            if _PYTEST_DOCS_RE.match(lines[index])
        ),
        None,
    )
    if docs_index is None:
        return text
    block = "\n".join(lines[header_index : docs_index + 1])
    if not _is_rm_rf_warnings_noise(block):
        return text
    kept = lines[:header_index] + lines[docs_index + 1 :]
    return "\n".join(_remove_status_line_warnings_count(kept))


def _strip_unbannered_tail_rm_rf(text: str) -> str:
    """Strip a trailing run of unbannered ``(rm_rf)`` warning entries.

    pytest 9 emits GC-time ``(rm_rf)`` warnings *after* the results line, without
    a ``warnings summary`` header or a ``-- Docs:`` footer, so the banner-framed
    stripper cannot observe them. Each entry is a ``pathlib.py:N: PytestWarning:
    (rm_rf) …`` line followed by an ``OSError`` detail line and a
    ``warnings.warn(`` call. Only a trailing block that is entirely this known
    noise is removed; a genuine unbannered warning (e.g. a source
    ``DeprecationWarning``) is left intact so it still surfaces as drift.
    """
    lines = text.split("\n")
    last_content_index = -1
    for index, line in enumerate(lines):
        if line == "":
            continue
        rm_rf_entry = bool(_RM_RF_ENTRY_RE.match(line)) or bool(_RM_RF_OS_ERROR_RE.match(line))
        warn_call = (
            bool(_RM_RF_WARN_CALL_RE.match(line))
            and index > 0
            and bool(_RM_RF_OS_ERROR_RE.match(lines[index - 1]))
        )
        if rm_rf_entry or warn_call:
            continue
        last_content_index = index
    block = "\n".join(lines[last_content_index + 1 :])
    if not _RM_RF_ENTRY_RE.search(block):
        return text
    kept = lines[: last_content_index + 1]
    while kept and kept[-1] == "":
        kept.pop()
    return "\n".join(_remove_status_line_warnings_count(kept))


def _strip_pytest_warning_summary(text: str) -> str:
    """Drop pytest's environment-specific ``(rm_rf)`` warnings, if present.

    The warning embeds the random pytest base-temp path and fails ``ENOTEMPTY``
    cleanup on stale local state, so it is not reproducible and must not be part
    of a replay golden. It is removed only when every warning entry is that known
    noise; genuine warnings are left intact so they still surface as drift. Both
    the banner-framed ``warnings summary`` / ``-- Docs:`` layout (other pytest
    setups) and the unbannered trailing layout (pytest 9 GC-time) are handled.
    """
    text = _strip_banner_framed_rm_rf(text)
    text = _strip_unbannered_tail_rm_rf(text)
    return text


def _normalize_review_test_output(report: dict[str, Any]) -> None:
    """Normalize captured pytest output in a skill-review report for replay."""
    auto_review = report.get("auto_review")
    if not isinstance(auto_review, dict):
        raise ReplayError("skill review auto_review must be a mapping")
    output = auto_review.get("test_output")
    if isinstance(output, str):
        auto_review["test_output"] = _strip_pytest_warning_summary(output)


def _exact_payload_sha256(payload: Any) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(rendered).hexdigest()


def _normalize_text_file(path: Path) -> None:
    """Keep generated text artifacts byte-stable under the end-of-file fixer."""
    path.write_text(
        path.read_text(encoding="utf-8").rstrip("\n") + "\n", encoding="utf-8", newline="\n"
    )
