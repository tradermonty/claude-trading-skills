#!/usr/bin/env python3
"""Lint skill scripts for zero defaults on price-bar fields (issue #655).

Scans ``skills/*/scripts/**/*.py`` (any ``tests/`` directory excluded) with the
stdlib ``ast`` module. The fields are ``open``, ``high``, ``low``, ``close``,
``volume`` and ``adjClose``. A finding is:

- ``X.get("<field>", 0)`` / ``0.0`` / ``False``, positional or as the
  ``default=`` keyword (pandas ``Series.get``), including a nested default
  such as ``d.get("close", d.get("adjClose", 0))`` (reported on the inner field);
- ``X.get("<field>") or 0`` / ``or 0.0`` / ``or False`` (a two-operand ``or``);
- ``X.get("<field>", 0.0) or 0.0`` counts once, as the ``get`` finding.

A missing or non-finite bar value must be read with the vendored
``_price_bars.read_price`` helper and handled as missing, never as ``0``.

Not detected (known limits): variable field names (``bar.get(k, 0)``),
capitalized yfinance keys (``"Close"``), ``-0.0`` defaults, subscripts such as
``x["close"] or 0``, longer chains such as ``a or b or 0``, quote ``price``
fields, and stockbee-episodic-pivot-analyzer ``analyze_ep.py:513-514``.

Ratchet: ``config/price-bar-default-allowlist.json`` lists the sites not yet
migrated. Each entry is ``{path, scope, field, count, reason}``, where ``scope``
is the enclosing qualname (``Class.method``, ``outer.inner``) or ``<module>``.
``count`` must equal the number of findings for that ``(path, scope, field)``
key: more, fewer or none all fail, so the allowlist can only shrink.

Exit codes: 0 clean, 1 findings or an invalid/stale allowlist.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALLOWLIST = ROOT / "config" / "price-bar-default-allowlist.json"
FIELDS = frozenset({"open", "high", "low", "close", "volume", "adjClose"})
MODULE_SCOPE = "<module>"


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    field: str
    scope: str
    form: str

    def format(self) -> str:
        return (
            f"{self.path}:{self.line}: {self.field}: zero-default read `{self.form}` "
            f"in {self.scope}; use _price_bars.read_price and handle missing data"
        )


def _is_zero(node: ast.AST) -> bool:
    # 0, 0.0 and False (False == 0 in arithmetic). ``-0.0`` parses as a UnaryOp,
    # not a Constant, so it is not matched.
    return (
        isinstance(node, ast.Constant)
        and type(node.value) in (int, float, bool)
        and node.value == 0
    )


def _get_field(node: ast.AST) -> str | None:
    """Return the field of ``X.get("<field>", ...)``, else ``None``."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and node.args[0].value in FIELDS
    ):
        return node.args[0].value
    return None


def _has_zero_default(call: ast.Call) -> bool:
    """Positional ``get(f, 0)`` or keyword ``get(f, default=0)`` (pandas-style)."""
    if len(call.args) >= 2 and _is_zero(call.args[1]):
        return True
    return any(kw.arg == "default" and _is_zero(kw.value) for kw in call.keywords)


class _Visitor(ast.NodeVisitor):
    def __init__(self, rel: str) -> None:
        self.rel = rel
        self.findings: list[Finding] = []
        self._scope: list[str] = []

    def _scope_name(self) -> str:
        return ".".join(self._scope) if self._scope else MODULE_SCOPE

    def _enter(self, node: ast.AST, name: str) -> None:
        self._scope.append(name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter(node, node.name)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._enter(node, node.name)

    def _add(self, node: ast.AST, field: str, form: str) -> None:
        self.findings.append(Finding(self.rel, node.lineno, field, self._scope_name(), form))

    def visit_Call(self, node: ast.Call) -> None:
        field = _get_field(node)
        if field and _has_zero_default(node):
            self._add(node, field, ast.unparse(node))
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if isinstance(node.op, ast.Or) and len(node.values) == 2 and _is_zero(node.values[1]):
            left = node.values[0]
            field = _get_field(left)
            # get(<field>, 0) or 0 is already counted by visit_Call.
            if field and not _has_zero_default(left):  # type: ignore[arg-type]
                self._add(node, field, ast.unparse(node))
        self.generic_visit(node)


def scan_source(source: str, rel: str) -> list[Finding]:
    visitor = _Visitor(rel)
    visitor.visit(ast.parse(source, filename=rel))
    return sorted(visitor.findings, key=lambda f: (f.line, f.field))


def scan_file(path: Path, rel: str) -> list[Finding]:
    return scan_source(path.read_text(encoding="utf-8"), rel)


def iter_script_files(root: Path):
    for path in sorted((root / "skills").glob("*/scripts/**/*.py")):
        parts = path.relative_to(root).parts
        if "tests" in parts or "__pycache__" in parts:
            continue
        yield path


def load_allowlist(path: Path) -> tuple[list[dict], list[str]]:
    """Return (entries, errors). A missing file is an empty allowlist."""
    if not path.exists():
        return [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], [f"{path.name}: invalid JSON: {exc}"]
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return [], [f"{path.name}: expected an object with an 'entries' list"]
    errors: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    valid: list[dict] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"{path.name}: entry {i} is not an object")
            continue
        ok = True
        for key in ("path", "scope", "field", "reason"):
            value = entry.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{path.name}: entry {i} missing non-empty '{key}'")
                ok = False
        count = entry.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            errors.append(f"{path.name}: entry {i} needs a positive integer 'count'")
            ok = False
        if isinstance(entry.get("field"), str) and entry["field"] not in FIELDS:
            errors.append(f"{path.name}: entry {i} has unknown field {entry['field']!r}")
            ok = False
        if not ok:
            continue
        key = (entry["path"], entry["scope"], entry["field"])
        if key in seen:
            errors.append(f"{path.name}: duplicate entry for {key}")
            continue
        seen.add(key)
        valid.append(entry)
    return valid, errors


def run(root: Path, allowlist_path: Path) -> tuple[list[str], int, int]:
    """Return (problem lines, scanned file count, total finding count)."""
    entries, problems = load_allowlist(allowlist_path)
    if problems:
        return problems, 0, 0
    allowed = {(e["path"], e["scope"], e["field"]): e["count"] for e in entries}
    findings: list[Finding] = []
    files = 0
    for path in iter_script_files(root):
        files += 1
        findings.extend(scan_file(path, path.relative_to(root).as_posix()))
    actual = Counter((f.path, f.scope, f.field) for f in findings)
    lines = [f.format() for f in findings if (f.path, f.scope, f.field) not in allowed]
    for key, expected in sorted(allowed.items()):
        found = actual.get(key, 0)
        if found != expected:
            path, scope, field = key
            lines.append(
                f"{allowlist_path.name}: {path} scope={scope} field={field}: "
                f"expected {expected} finding(s), found {found}; update the count "
                "(or remove the entry once the sites are migrated)"
            )
    return lines, files, len(findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--allowlist", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    allowlist = args.allowlist or (root / "config" / "price-bar-default-allowlist.json")
    lines, files, total = run(root, allowlist)
    if lines:
        for line in lines:
            print(line, file=sys.stderr)
        print(f"{len(lines)} price-bar zero-default problem(s).", file=sys.stderr)
        return 1
    print(
        f"Price-bar defaults OK ({files} script files scanned, "
        f"{total} allowlisted finding(s) pending migration)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
