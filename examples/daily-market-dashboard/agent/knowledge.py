"""Knowledge-folder helpers based on markdown + ripgrep search."""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agent.path_utils import is_within

logger = logging.getLogger(__name__)

_EN_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "how",
    "i",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "we",
    "what",
    "when",
    "where",
    "who",
    "why",
    "with",
    "would",
    "you",
}


@dataclass
class KnowledgeMatch:
    """One line-level search hit from the knowledge folder."""

    path: str
    line: int
    snippet: str


def resolve_knowledge_dir(project_root: Path, knowledge_dir: str) -> Path:
    """Resolve knowledge directory and ensure it stays within project root."""
    root = project_root.resolve()
    candidate = Path(knowledge_dir)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not is_within(resolved, root):
        raise ValueError("Knowledge directory must be inside the project root.")
    return resolved


def list_knowledge_markdown_files(knowledge_dir: Path, project_root: Path) -> list[str]:
    """Return sorted project-relative markdown paths under the knowledge folder."""
    if not knowledge_dir.exists():
        return []
    root = project_root.resolve()
    files: list[str] = []
    for path in sorted(knowledge_dir.rglob("*.md")):
        if path.is_file():
            files.append(str(path.resolve().relative_to(root)))
    return files


def search_knowledge_markdown(
    query: str,
    *,
    knowledge_dir: Path,
    project_root: Path,
    max_hits: int,
) -> list[KnowledgeMatch]:
    """Search knowledge markdown files with rg and return line-level hits."""
    if not query.strip():
        return []
    if not knowledge_dir.exists():
        return []
    pattern = build_knowledge_pattern(query)
    if not pattern:
        return []

    try:
        output = _run_rg_search(
            pattern=pattern,
            knowledge_dir=knowledge_dir,
            project_root=project_root,
        )
        return _parse_rg_output(output, knowledge_dir=knowledge_dir, project_root=project_root)[
            :max_hits
        ]
    except FileNotFoundError:
        logger.info("rg command is unavailable; falling back to Python search")
    except subprocess.TimeoutExpired:
        logger.warning("rg knowledge search timed out")
        return []
    except Exception:
        logger.exception("Knowledge search via rg failed")
        return []

    return _fallback_python_search(
        pattern=pattern,
        knowledge_dir=knowledge_dir,
        project_root=project_root,
        max_hits=max_hits,
    )


def build_knowledge_pattern(query: str) -> str:
    """Build a safe OR pattern from query terms for ripgrep usage."""
    terms: list[str] = []
    seen: set[str] = set()
    for token in re.split(r"\s+", query.strip()):
        normalized = token.strip().strip("`'\".,!?():;[]{}")
        if not normalized:
            continue
        lowered = normalized.lower()
        if normalized.isascii() and lowered in _EN_STOPWORDS:
            continue
        # Keep meaningful single-character CJK tokens while skipping noisy ASCII one-letter tokens.
        if len(normalized) < 2 and len(query.strip()) > 2 and normalized.isascii():
            continue
        if lowered in seen:
            continue
        terms.append(normalized)
        seen.add(lowered)
        if len(terms) >= 4:
            break
    if not terms and query.strip():
        terms = [query.strip()]
    return "|".join(_to_rg_pattern_term(term) for term in terms)


def _to_rg_pattern_term(term: str) -> str:
    escaped = re.escape(term)
    if term.isascii() and re.fullmatch(r"[A-Za-z0-9_]+", term):
        return rf"\b{escaped}\b"
    return escaped


def build_knowledge_preamble(files: list[str], matches: list[KnowledgeMatch]) -> str:
    """Create a compact prompt section for available knowledge and search hits."""
    if not files and not matches:
        return ""

    lines = ["[KNOWLEDGE]"]
    if files:
        lines.append("Available markdown files under knowledge/:")
        for file_path in files[:50]:
            lines.append(f"- {file_path}")
    if matches:
        lines.append("Search hits from knowledge/:")
        for match in matches:
            lines.append(f"- {match.path}:{match.line}: {match.snippet}")
    else:
        lines.append("No direct keyword hit was found in knowledge/.")
    lines.append("Use knowledge paths above as the primary reference when relevant.")
    return "\n".join(lines)


def _run_rg_search(*, pattern: str, knowledge_dir: Path, project_root: Path) -> str:
    result = subprocess.run(
        [
            "rg",
            "-n",
            "--no-heading",
            "-S",
            "--glob",
            "*.md",
            pattern,
            str(knowledge_dir),
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
        cwd=str(project_root.resolve()),
    )
    # rg returns 0 for matches, 1 for no matches.
    if result.returncode not in {0, 1}:
        logger.warning("rg returned non-zero status: %s", result.returncode)
    return result.stdout


def _parse_rg_output(
    output: str, *, knowledge_dir: Path, project_root: Path
) -> list[KnowledgeMatch]:
    matches: list[KnowledgeMatch] = []
    root = project_root.resolve()
    knowledge_root = knowledge_dir.resolve()

    for raw_line in output.splitlines():
        parts = raw_line.split(":", 2)
        if len(parts) != 3:
            continue
        raw_path, raw_line_no, snippet = parts
        try:
            line_no = int(raw_line_no)
        except ValueError:
            continue

        path = Path(raw_path)
        resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
        if not is_within(resolved, knowledge_root):
            continue

        rel_path = str(resolved.relative_to(root))
        matches.append(KnowledgeMatch(path=rel_path, line=line_no, snippet=snippet.strip()))

    return matches


def _fallback_python_search(
    *,
    pattern: str,
    knowledge_dir: Path,
    project_root: Path,
    max_hits: int,
) -> list[KnowledgeMatch]:
    compiled = re.compile(pattern, re.IGNORECASE)
    root = project_root.resolve()
    matches: list[KnowledgeMatch] = []

    for path in sorted(knowledge_dir.rglob("*.md")):
        if not path.is_file():
            continue
        rel_path = str(path.resolve().relative_to(root))
        for index, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if compiled.search(line):
                matches.append(KnowledgeMatch(path=rel_path, line=index, snippet=line.strip()))
                if len(matches) >= max_hits:
                    return matches
    return matches
