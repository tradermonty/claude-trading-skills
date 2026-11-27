"""Pick the claude CLI that the scheduled automation runs (issue #652).

A machine can have several `claude` executables on PATH, for example an old
Homebrew copy ahead of the native installer's `~/.local/bin/claude`. An old
CLI answers the review prompt in prose instead of JSON, so the improvement
loop could never record a successful run. Instead of trusting PATH order,
probe every candidate and use the newest version.

`SKILL_LOOP_CLAUDE_BIN` pins an explicit executable. An unusable pin is an
error rather than a silent fallback, so a typo cannot hide behind PATH.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional

CLAUDE_BIN_ENV = "SKILL_LOOP_CLAUDE_BIN"
VERSION_TIMEOUT_S = 15
_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")

Version = Optional[tuple[int, int, int]]


class ClaudeBinError(Exception):
    """The pinned claude executable cannot be used."""


@dataclass
class ClaudeChoice:
    path: str
    version: Version
    source: str  # "override" or "path"
    candidates: list[tuple[str, Version]] = field(default_factory=list)


def _is_executable(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def _candidates(path: str) -> list[str]:
    seen: set[str] = set()
    found: list[str] = []
    for directory in path.split(os.pathsep):
        # An empty entry means the current directory, as in a shell lookup.
        # Anchor relative entries now: the jobs later run commands from a
        # different working directory.
        exe = os.path.abspath(os.path.join(directory or os.curdir, "claude"))
        if not _is_executable(exe):
            continue
        real = os.path.realpath(exe)
        if real in seen:
            continue
        seen.add(real)
        found.append(exe)
    return found


def probe_version(exe: str) -> Version:
    """Return (major, minor, patch) from `exe --version`, or None."""
    try:
        result = subprocess.run(
            [exe, "--version"],
            capture_output=True,
            text=True,
            errors="replace",  # an odd banner must not abort the job
            check=False,
            timeout=VERSION_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    match = _VERSION_RE.search(result.stdout or "")
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def resolve_claude_bin(path: str | None = None) -> ClaudeChoice | None:
    """Return the claude executable to run, or None when there is none.

    Raises ClaudeBinError when SKILL_LOOP_CLAUDE_BIN names an unusable file.
    """
    override = os.environ.get(CLAUDE_BIN_ENV, "").strip()
    if override:
        # A bare or relative pin would be looked up again at run time, from
        # another directory or through PATH, so require an absolute path.
        if not os.path.isabs(override) or not _is_executable(override):
            raise ClaudeBinError(
                f"{CLAUDE_BIN_ENV} must be an absolute path to an executable file: {override}"
            )
        return ClaudeChoice(
            path=override, version=None, source="override", candidates=[(override, None)]
        )

    found = _candidates(os.environ.get("PATH", "") if path is None else path)
    if not found:
        return None
    if len(found) == 1:
        # Nothing to choose between, so skip the version probe.
        return ClaudeChoice(
            path=found[0], version=None, source="path", candidates=[(found[0], None)]
        )

    ranked = [(exe, probe_version(exe)) for exe in found]
    # Newest known version wins; an unreadable version ranks below all known
    # ones; ties keep PATH order (max() returns the first maximal item).
    best = max(ranked, key=lambda item: (item[1] is not None, item[1] or (0, 0, 0)))
    return ClaudeChoice(path=best[0], version=best[1], source="path", candidates=ranked)


def describe(choice: ClaudeChoice) -> str:
    """One log line naming the chosen CLI and any older copies it skipped."""

    def fmt(version: Version) -> str:
        return ".".join(map(str, version)) if version else "unknown"

    text = f"Using claude CLI {choice.path} (version {fmt(choice.version)}, {choice.source})"
    skipped = [f"{exe} ({fmt(v)})" for exe, v in choice.candidates if exe != choice.path]
    if skipped:
        text += "; skipped " + ", ".join(skipped)
    return text
