#!/usr/bin/env python3
"""Lint skill scripts for CLI error conventions (issue #497).

Scans ``skills/*/scripts/**/*.py`` (tests excluded) with the stdlib ``ast``
module and flags:

``stderr-error-print``
    ``print(...)`` whose first argument is a string literal / f-string starting
    with ``Error``, ``ERROR`` or ``FATAL`` (leading whitespace, emoji and
    punctuation are ignored) and that has no ``file=...stderr`` keyword.
``import-error-exit1``
    An ``except ImportError`` (or ``ModuleNotFoundError``) handler, at module
    or function scope, that exits 1: ``sys.exit(1)``, ``raise SystemExit(1)``,
    or ``sys.exit("msg")`` / ``raise SystemExit("msg")`` (a string argument
    means exit status 1). Missing runtime dependencies must exit 2. A bare
    ``raise`` after printing a hint is left unflagged. Limitation: guards of
    the form ``if requests is None: ... sys.exit(1)`` are not detected.
``network-timeout``
    ``urlopen(...)``, ``requests.<verb>(...)`` or ``<session>.<verb>(...)``
    without a ``timeout=`` keyword (or with ``timeout=None``). A receiver
    counts as an HTTP session when its last name component is assigned from
    ``requests.Session()`` / ``Session()`` in the same module, or is exactly
    ``session`` / ``sess`` / ``*_session`` and the call has at least one
    positional argument or ``url=``. So ``session_state.get("k")`` and
    ``cache.get(key)`` are not flagged.

Intentional exceptions live in ``config/cli-error-allowlist.json``. Each entry
needs ``path``, ``rule``, ``scope`` (the enclosing function qualname, or
``<module>``; line independent) and a non-empty ``reason``. An entry that no
longer matches any finding is stale and fails the check.

Exit codes: 0 clean, 1 findings or stale/invalid allowlist.
Findings are printed to stderr as ``path:line: rule: message``.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALLOWLIST = ROOT / "config" / "cli-error-allowlist.json"

RULE_PRINT = "stderr-error-print"
RULE_IMPORT = "import-error-exit1"
RULE_TIMEOUT = "network-timeout"
RULES = (RULE_PRINT, RULE_IMPORT, RULE_TIMEOUT)

ERROR_PREFIXES = ("Error", "ERROR", "FATAL")
HTTP_VERBS = {"get", "post", "put", "delete", "patch", "head", "request"}
IMPORT_EXC = {"ImportError", "ModuleNotFoundError"}
MODULE_SCOPE = "<module>"


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    scope: str
    message: str

    def format(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.message}"


def _leading_text(node: ast.expr) -> str | None:
    """Return the leading literal text of a str constant or f-string."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr) and node.values:
        first = node.values[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    return None


def _starts_with_error(text: str) -> bool:
    stripped = text.lstrip()
    # Ignore leading emoji / punctuation (trivial decoration only).
    i = 0
    while i < len(stripped) and not stripped[i].isalnum():
        i += 1
    return stripped[i:].startswith(ERROR_PREFIXES)


def _has_stderr_file(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg == "file":
            return "stderr" in ast.unparse(kw.value)
    return False


def _is_exit_one(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    name = ast.unparse(node.func)
    if name not in {"sys.exit", "exit", "quit"}:
        return False
    return (
        len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == 1
        and not isinstance(node.args[0].value, bool)
    )


def _is_str_arg(node: ast.expr) -> bool:
    """True for a str literal or f-string (an exit with it means status 1)."""
    return isinstance(node, ast.JoinedStr) or (
        isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


def _is_exit_string(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if ast.unparse(node.func) not in {"sys.exit", "exit", "quit"}:
        return False
    return len(node.args) == 1 and _is_str_arg(node.args[0])


def _is_raise_systemexit_one(node: ast.AST) -> bool:
    if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
        if ast.unparse(node.exc.func) == "SystemExit" and len(node.exc.args) == 1:
            arg = node.exc.args[0]
            if isinstance(arg, ast.Constant) and arg.value == 1 and not isinstance(arg.value, bool):
                return True
            return _is_str_arg(arg)
    return False


def _catches_import_error(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return False
    types = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(ast.unparse(t).split(".")[-1] in IMPORT_EXC for t in types)


def _walk_no_defs(nodes: list[ast.stmt]):
    """Yield nodes without descending into function or class definitions."""
    stack = list(nodes)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                stack.append(child)


SESSION_FACTORIES = {"requests.Session", "requests.session", "Session"}


def _last_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _session_names(tree: ast.AST) -> set[str]:
    """Last name components assigned from ``requests.Session()`` in the module."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if isinstance(value, ast.Call) and ast.unparse(value.func) in SESSION_FACTORIES:
            for target in targets:
                name = _last_name(target)
                if name:
                    names.add(name)
    return names


def _looks_like_session_name(last: str) -> bool:
    return last in {"session", "sess"} or last.endswith("_session")


def _has_url_argument(call: ast.Call) -> bool:
    return bool(call.args) or any(kw.arg == "url" for kw in call.keywords)


def _network_call_name(call: ast.Call, sessions: frozenset[str] = frozenset()) -> str | None:
    func = call.func
    if isinstance(func, ast.Name) and func.id == "urlopen":
        return "urlopen"
    if isinstance(func, ast.Attribute):
        if func.attr == "urlopen":
            return ast.unparse(func)
        if func.attr in HTTP_VERBS:
            last = (_last_name(func.value) or "").lower()
            if last == "requests":
                return ast.unparse(func)
            if _last_name(func.value) in sessions:
                return ast.unparse(func)
            if _looks_like_session_name(last) and _has_url_argument(call):
                return ast.unparse(func)
    return None


def _timeout_missing(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg == "timeout":
            return isinstance(kw.value, ast.Constant) and kw.value.value is None
        if kw.arg is None:
            return False  # **kwargs may carry a timeout; cannot tell statically.
    return True


class _Visitor(ast.NodeVisitor):
    def __init__(self, rel: str, sessions: frozenset[str] = frozenset()) -> None:
        self.rel = rel
        self._sessions = sessions
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

    def visit_Try(self, node: ast.Try) -> None:
        for handler in node.handlers:
            if not _catches_import_error(handler):
                continue
            for inner in _walk_no_defs(handler.body):
                if _is_exit_one(inner) or _is_exit_string(inner) or _is_raise_systemexit_one(inner):
                    self.findings.append(
                        Finding(
                            self.rel,
                            inner.lineno,
                            RULE_IMPORT,
                            self._scope_name(),
                            "missing dependency exits 1; exit 2 with a requirements.txt hint",
                        )
                    )
        self.generic_visit(node)

    visit_TryStar = visit_Try  # type: ignore[assignment]

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "print" and node.args:
            text = _leading_text(node.args[0])
            if text is not None and _starts_with_error(text) and not _has_stderr_file(node):
                self.findings.append(
                    Finding(
                        self.rel,
                        node.lineno,
                        RULE_PRINT,
                        self._scope_name(),
                        "error message printed to stdout; add file=sys.stderr",
                    )
                )
        name = _network_call_name(node, self._sessions)
        if name and _timeout_missing(node):
            self.findings.append(
                Finding(
                    self.rel,
                    node.lineno,
                    RULE_TIMEOUT,
                    self._scope_name(),
                    f"{name}(...) has no bounded timeout= argument",
                )
            )
        self.generic_visit(node)


def scan_file(path: Path, rel: str) -> list[Finding]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    except SyntaxError as exc:
        return [Finding(rel, exc.lineno or 1, "syntax-error", MODULE_SCOPE, str(exc.msg))]
    visitor = _Visitor(rel, frozenset(_session_names(tree)))
    visitor.visit(tree)
    findings = visitor.findings
    return sorted(findings, key=lambda f: (f.line, f.rule))


def iter_script_files(root: Path):
    for path in sorted((root / "skills").glob("*/scripts/**/*.py")):
        rel_parts = path.relative_to(root).parts
        if "tests" in rel_parts or "__pycache__" in rel_parts:
            continue
        if path.name.startswith("test_") or path.name == "conftest.py":
            continue
        yield path


def load_allowlist(path: Path) -> tuple[list[dict], list[str]]:
    """Return (entries, errors)."""
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
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"{path.name}: entry {i} is not an object")
            continue
        for key in ("path", "rule", "scope", "reason"):
            value = entry.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{path.name}: entry {i} missing non-empty '{key}'")
        if entry.get("rule") not in RULES:
            errors.append(f"{path.name}: entry {i} has unknown rule {entry.get('rule')!r}")
    return entries, errors


def run(root: Path, allowlist_path: Path) -> tuple[list[str], int]:
    """Return (problem lines, scanned file count)."""
    entries, problems = load_allowlist(allowlist_path)
    if problems:
        return problems, 0
    used: set[int] = set()
    lines: list[str] = []
    count = 0
    for path in iter_script_files(root):
        count += 1
        rel = path.relative_to(root).as_posix()
        for finding in scan_file(path, rel):
            matched = [
                i
                for i, e in enumerate(entries)
                if e["path"] == finding.path
                and e["rule"] == finding.rule
                and e["scope"] == finding.scope
            ]
            if matched:
                used.update(matched)
            else:
                lines.append(finding.format())
    for i, e in enumerate(entries):
        if i not in used:
            lines.append(
                f"{allowlist_path.name}: stale allowlist entry "
                f"{e['path']} [{e['rule']}] scope={e['scope']}: matches nothing; remove it"
            )
    return lines, count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--allowlist", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    allowlist = args.allowlist or (root / "config" / "cli-error-allowlist.json")
    lines, count = run(root, allowlist)
    if lines:
        for line in lines:
            print(line, file=sys.stderr)
        print(f"{len(lines)} CLI error-convention problem(s).", file=sys.stderr)
        return 1
    print(f"CLI error conventions OK ({count} script files scanned).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
