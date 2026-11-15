"""Fail closed when canonical private paths occur in the active Git index.

This is a path guard, not a content/PII scanner. Never echo indexed paths/data.
"""

import collections
import os
import subprocess
import sys

PRIVATE_ROOTS = {
    "state",
    "reports",
    "logs",
    "reviews",
    ".cache",
    ".claude",
    ".staging",
    "private-backups",
    ".aws",
    ".ssh",
}
PLACEHOLDERS = {"state/journal/.gitkeep", "state/theses/.gitkeep"}


def git(*args, data=None):
    return subprocess.run(
        ["git", *args], input=data, capture_output=True, check=True, timeout=30
    ).stdout


def main():
    violations = collections.Counter()
    try:
        records = git("ls-files", "--stage", "--full-name", "-z", "--", ":/")
        for record in records.split(b"\0"):
            if not record:
                continue
            metadata, raw_path = record.split(b"\t", 1)
            mode, oid, stage = metadata.split()
            path = os.fsdecode(raw_path)
            root = path.split("/", 1)[0].lower()
            private = root in PRIVATE_ROOTS
            credential = root == ".env" or root.startswith((".env.", ".envrc", ".mcp.json"))
            if not (private or credential):
                continue
            if path in PLACEHOLDERS and mode in (b"100644", b"100755") and stage == b"0":
                info = git(
                    "--no-replace-objects", "cat-file", "--batch-check", data=oid + b"\n"
                ).split()
                if info == [oid, b"blob", b"0"]:
                    continue
            violations["credentials" if credential else "private-data"] += 1
    except (OSError, ValueError, subprocess.SubprocessError):
        print("Private-path audit failed: Git index inspection unavailable.", file=sys.stderr)
        return 1
    if violations:
        summary = ", ".join(f"{key}={count}" for key, count in sorted(violations.items()))
        print(f"Private-path audit blocked indexed entries: {summary}", file=sys.stderr)
        return 1
    print("Private-path audit passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
