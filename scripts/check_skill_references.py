#!/usr/bin/env python3
"""Validate literal skill-relative resources mentioned in every SKILL.md.

Repository-qualified paths, URLs, and templated/glob examples are outside this
bundled-resource gate. Concrete relative paths in prose, code and Markdown
links are checked, including directories. No user-defined filename exemption
is inferred from a CLI flag or filename prefix.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Keep the left boundary: do not extract scripts/foo.py from skills/x/scripts/foo.py.
# Also skip identifier prefixes such as my_references/, while allowing _emphasis_.
RESOURCE = re.compile(
    r"(?<![A-Za-z0-9/.-])(?<![A-Za-z0-9]_)(?:\./|(?:\.\./)+)?(?:references|scripts|assets)/"
    r"[^\s`\"'(),;]+"
)
# Trailing punctuation, emphasis markers, unmatched closers, and a :line suffix.
CLOSERS = {"]": "[", ">": "<", "}": "{"}
LINE_SUFFIX = re.compile(r":\d+(?::\d+)?\Z")
# These instructions deliberately refer to the central repository, not a bundle.
REPO_RESOURCES = {
    ("kanchi-dividend-sop", "scripts/run_all_tests.sh"),
    ("skill-idea-miner", "scripts/run_skill_generation_pipeline.py"),
    ("us-undervalued-growth-screener", "scripts/fmp_client/"),
}


def _trim(token: str, prefix: str) -> str:
    """Drop prose wrapping after a path. Emphasis is stripped only when the same
    marker opens earlier on the line, so a trailing glob (scripts/test_*) stays."""
    while True:
        trimmed = LINE_SUFFIX.sub("", token.rstrip(".:!?"))
        marker = trimmed[len(trimmed.rstrip("*_")) :]
        if marker and marker in prefix:
            trimmed = trimmed[: -len(marker)]
        if trimmed and trimmed[-1] in CLOSERS and CLOSERS[trimmed[-1]] not in trimmed:
            trimmed = trimmed[:-1]
        if trimmed == token:
            return token
        token = trimmed


def references(text: str):
    """Yield (line, path) for literal relative resource tokens."""
    for lineno, line in enumerate(text.splitlines(), 1):
        for match in RESOURCE.finditer(line):
            token = _trim(match.group(), line[: match.start()])
            token = token.split("#", 1)[0]
            if token and not any(char in token for char in "*?$%<>{}[]"):
                yield lineno, token


def check(root: Path) -> list[str]:
    """Return actionable errors; never read a referenced resource's contents."""
    errors = []
    documents = sorted((root / "skills").glob("*/SKILL.md"))
    if not documents:
        return ["skills/: no SKILL.md files found"]
    for document in documents:
        label = document.relative_to(root).as_posix()
        try:
            content = document.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{label}: cannot read: {exc}")
            continue
        for lineno, resource in references(content):
            base = root if (document.parent.name, resource) in REPO_RESOURCES else document.parent
            target = base / resource
            try:
                if ".." in Path(resource).parts:
                    errors.append(f"{label}:{lineno}: resource escapes skill: {resource}")
                elif not target.resolve().is_relative_to(base.resolve()):
                    errors.append(f"{label}:{lineno}: resource escapes bundle: {resource}")
                elif not target.exists():
                    errors.append(f"{label}:{lineno}: missing resource: {resource}")
            except (OSError, RuntimeError) as exc:
                errors.append(f"{label}:{lineno}: cannot resolve {resource}: {exc}")
    return errors


def main() -> int:
    errors = check(ROOT)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    print("All SKILL.md relative resource references exist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
