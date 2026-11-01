#!/usr/bin/env python3
"""Report hand-maintained skill-guide drift without executing documented code."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLAG_RE = re.compile(r"(?<![\w-])--[A-Za-z][A-Za-z0-9-]*")


def _git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=10,
            env={key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def history_status(root: Path) -> dict:
    head = _git(root, "rev-parse", "HEAD")
    shallow = _git(root, "rev-parse", "--is-shallow-repository")
    complete = head is not None and shallow == "false"
    return {
        "head": head,
        "complete": complete,
        "reason": None
        if complete
        else ("shallow git history" if shallow == "true" else "git history unavailable"),
    }


def last_commit_time(root: Path, path: Path) -> int | None:
    text = _git(root, "log", "-1", "--format=%ct", "--", path.relative_to(root).as_posix())
    return int(text) if text and text.isdigit() else None


def _generated(text: str) -> bool:
    if not text.startswith("---\n"):
        return False
    frontmatter = text.split("---", 2)
    return len(frontmatter) == 3 and bool(
        re.search(
            r"^generated:\s*true\s*(?:#.*)?$",
            frontmatter[1],
            re.MULTILINE | re.IGNORECASE,
        )
    )


def python_blocks(text: str):
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        match = re.fullmatch(r"(`{3,}|~{3,})(?:python|python3|py)\s*", lines[i].strip())
        if not match:
            i += 1
            continue
        fence = match.group(1)
        first = i + 2
        body = []
        i += 1
        while i < len(lines) and not re.fullmatch(
            re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*",
            lines[i].strip(),
        ):
            body.append(lines[i])
            i += 1
        yield first, "\n".join(body)
        i += 1


def _literal_search_path(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    # Explicit supported bootstrap: str(Path("repo/relative/scripts").resolve()).
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "str"
        and len(node.args) == 1
    ):
        resolved = node.args[0]
        if (
            isinstance(resolved, ast.Call)
            and isinstance(resolved.func, ast.Attribute)
            and resolved.func.attr == "resolve"
            and not resolved.args
        ):
            path = resolved.func.value
            if (
                isinstance(path, ast.Call)
                and isinstance(path.func, ast.Name)
                and path.func.id == "Path"
                and len(path.args) == 1
            ):
                return _literal_search_path(path.args[0])
    return None


def _search_paths(tree: ast.Module, root: Path, before_line: int) -> set[Path]:
    paths = set()
    for statement in tree.body:
        if not isinstance(statement, ast.Expr) or statement.lineno >= before_line:
            continue
        node = statement.value
        if not isinstance(node, ast.Call):
            continue
        name = ast.unparse(node.func)
        index = 1 if name == "sys.path.insert" else 0
        if name not in {"sys.path.insert", "sys.path.append"} or len(node.args) <= index:
            continue
        value = _literal_search_path(node.args[index])
        if value is not None:
            path = (root / value).resolve()
            if path.is_relative_to(root) and path.is_dir():
                paths.add(path)
    return paths


def _module_path(base: Path, module: str) -> Path | None:
    path = base.joinpath(*module.split("."))
    if path.with_suffix(".py").is_file():
        return path.with_suffix(".py")
    if path.is_dir():
        return path / "__init__.py" if (path / "__init__.py").is_file() else path
    return None


def _exports(path: Path) -> set[str] | None:
    if not path.is_file():
        return None  # Namespace-package exports cannot be inferred here.
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == "__getattr__":
                return None
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if any(alias.name == "*" for alias in node.names):
                return None
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(
                t.id for target in targets for t in ast.walk(target) if isinstance(t, ast.Name)
            )
    return names


def import_checks(text: str, root: Path, skill_dir: Path) -> tuple[list[dict], list[dict]]:
    findings, unchecked = [], []
    scripts = skill_dir / "scripts"
    locals_ = (
        {p.stem for p in scripts.glob("*.py")} | {p.name for p in scripts.iterdir() if p.is_dir()}
        if scripts.is_dir()
        else set()
    )
    stdlib = getattr(sys, "stdlib_module_names", frozenset(sys.builtin_module_names))
    for first, block in python_blocks(text):
        try:
            tree = ast.parse(block)
        except SyntaxError as exc:
            findings.append(
                {
                    "category": "python_syntax_error",
                    "line": first + (exc.lineno or 1) - 1,
                    "detail": "Python example does not parse",
                }
            )
            continue
        for node in ast.walk(tree):
            line = first + getattr(node, "lineno", 1) - 1
            if isinstance(node, ast.Call) and (
                ast.unparse(node.func) == "__import__"
                or ast.unparse(node.func).endswith(".import_module")
            ):
                unchecked.append(
                    {"kind": "dynamic", "line": line, "module": ast.unparse(node.func)}
                )
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if node not in tree.body:
                unchecked.append({"kind": "conditional", "line": line, "module": ast.unparse(node)})
                continue
            if isinstance(node, ast.ImportFrom) and node.level:
                unchecked.append({"kind": "relative", "line": line, "module": node.module})
                continue
            modules = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            for module in modules:
                top = module.split(".")[0]
                if top in stdlib:
                    continue
                local = top in locals_
                if top != "skills" and not local:
                    unchecked.append({"kind": "external", "line": line, "module": module})
                    continue
                if local and scripts.resolve() not in _search_paths(tree, root, node.lineno):
                    findings.append(
                        {
                            "category": "missing_local_bootstrap",
                            "line": line,
                            "detail": f"Local import {module} lacks a supported repository-root sys.path setup",
                        }
                    )
                    continue
                source = _module_path(scripts if local else root, module)
                if source is None:
                    findings.append(
                        {
                            "category": "missing_repository_import",
                            "line": line,
                            "detail": f"Repository import path does not exist: {module}",
                        }
                    )
                    continue
                if isinstance(node, ast.ImportFrom):
                    exports = _exports(source)
                    for alias in node.names:
                        if alias.name == "*" or exports is None:
                            unchecked.append({"kind": "exports", "line": line, "module": module})
                        elif alias.name not in exports and not (
                            source.name == "__init__.py" and _module_path(source.parent, alias.name)
                        ):
                            findings.append(
                                {
                                    "category": "missing_repository_symbol",
                                    "line": line,
                                    "detail": f"No static export {alias.name} in {module}",
                                }
                            )
    return findings, unchecked


def build_report(root: Path) -> dict:
    root = root.resolve()
    if not (root / "skills").is_dir() or not (root / "docs").is_dir():
        raise ValueError("root must contain skills/ and docs/")
    history = history_status(root)
    dates, pages = {}, []
    generated = 0
    for language in ("en", "ja"):
        for path in sorted((root / f"docs/{language}/skills").glob("*.md")):
            skill = root / "skills" / path.stem
            source = skill / "SKILL.md"
            if not source.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            if _generated(text):
                generated += 1
                continue
            source_text = source.read_text(encoding="utf-8")
            missing = sorted(set(FLAG_RE.findall(source_text)) - set(FLAG_RE.findall(text)))
            for file in (source, path):
                if file not in dates:
                    dates[file] = last_commit_time(root, file) if history["complete"] else None
            source_date, page_date = dates[source], dates[path]
            known = source_date is not None and page_date is not None
            findings, unchecked = import_checks(text, root, skill)
            if missing and (not known or source_date > page_date):
                findings.insert(
                    0,
                    {
                        "category": "newer_source_missing_flags"
                        if known
                        else "unknown_history_missing_flags",
                        "line": 1,
                        "detail": "Flags not mentioned by guide: " + ", ".join(missing),
                    },
                )
            pages.append(
                {
                    "skill": path.stem,
                    "language": language,
                    "file": path.relative_to(root).as_posix(),
                    "source_commit_time": source_date,
                    "page_commit_time": page_date,
                    "history_known": known,
                    "missing_flags": missing,
                    "findings": findings,
                    "unchecked_imports": unchecked,
                }
            )
    pages.sort(key=lambda p: (p["skill"], p["language"]))
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "history": history,
        "summary": {
            "hand_maintained_pages": len(pages),
            "generated_pages_excluded": generated,
            "drift_pages": sum(bool(p["findings"]) for p in pages),
            "findings": sum(len(p["findings"]) for p in pages),
            "unknown_history_pages": sum(not p["history_known"] for p in pages),
            "unchecked_imports": sum(len(p["unchecked_imports"]) for p in pages),
        },
        "pages": pages,
        "limitations": [
            "Missing SKILL.md flags and commit chronology are review signals, not semantic proof.",
            "Analysis never executes examples or imports their modules; external/dynamic/relative/conditional imports are unchecked.",
            "Local imports require preceding top-level literal sys.path entries or str(Path(literal).resolve()) bootstrap forms.",
            "Git timestamps describe committed history; uncommitted edits are analyzed as current content without a new commit date.",
        ],
    }


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def render_markdown(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "# Hand-maintained skill guide drift",
        "",
        f"Assessed HEAD: `{report['history']['head'] or 'unknown'}`",
        f"History: {report['history']['reason'] or 'complete'}",
        "",
        f"Drift pages: **{summary['drift_pages']}** / {summary['hand_maintained_pages']}; "
        f"findings: {summary['findings']}; unknown-history pages: {summary['unknown_history_pages']}; "
        f"unchecked imports: {summary['unchecked_imports']}.",
        "",
        "| Page | Category | Detail |",
        "| --- | --- | --- |",
    ]
    for page in report["pages"]:
        for item in page["findings"]:
            lines.append(
                f"| {_cell(page['file'])}:{item['line']} | {_cell(item['category'])} | {_cell(item['detail'])} |"
            )
    lines += ["", "## Limits", "", *[f"- {limit}" for limit in report["limitations"]], ""]
    return "\n".join(lines)


def _annotation(value: str, *, property_value=False) -> str:
    text = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return text.replace(":", "%3A").replace(",", "%2C") if property_value else text


def github_annotations(report: dict, limit=20) -> list[str]:
    warnings = []
    for page in report["pages"]:
        for item in page["findings"]:
            if len(warnings) >= limit:
                return warnings
            warnings.append(
                f"::warning file={_annotation(page['file'], property_value=True)},line={item['line']},"
                f"title=Skill guide drift::{_annotation(item['category'] + ': ' + item['detail'])}"
            )
    return warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--github", action="store_true", help="Emit at most 20 warning annotations")
    args = parser.parse_args(argv)
    try:
        if (
            args.json_output
            and args.markdown_output
            and args.json_output.resolve() == args.markdown_output.resolve()
        ):
            raise ValueError("JSON and Markdown outputs must be different files")
        report = build_report(args.root)
        markdown = render_markdown(report)
        for path, text in (
            (args.json_output, json.dumps(report, ensure_ascii=False, indent=2) + "\n"),
            (args.markdown_output, markdown),
        ):
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
    except (OSError, ValueError, SyntaxError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.github:
        print("\n".join(github_annotations(report)))
    if not args.markdown_output:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
