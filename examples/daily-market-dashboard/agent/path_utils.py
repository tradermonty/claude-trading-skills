"""Shared path safety helpers."""

from __future__ import annotations

from pathlib import Path


def is_within(path: Path, root: Path) -> bool:
    """Return True when path is equal to or inside root."""
    return path == root or root in path.parents
