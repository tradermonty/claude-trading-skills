"""Contract tests for the hand-maintained bilingual glossary."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GLOSSARY_PATHS = {
    "en": PROJECT_ROOT / "docs" / "en" / "glossary.md",
    "ja": PROJECT_ROOT / "docs" / "ja" / "glossary.md",
}
TERM_PATTERN = re.compile(
    r"^### (?P<heading>[^\n]+)\n"
    r"\{:\s+#(?P<term_id>[a-z0-9-]+)\s+\}\n\n"
    r"(?P<definition>[^\n]+)\n\n"
    r"\*\*(?:Used by|関連スキル):\*\* (?P<used_by>[^\n]+)$",
    re.MULTILINE,
)
SKILL_LINK_PATTERN = re.compile(
    r"\[[^\]]+\]\(\{\{ '/(?P<lang>en|ja)/skills/"
    r"(?P<slug>[a-z0-9-]+)/' \| relative_url \}\}\)"
)
REQUIRED_TERM_IDS = {
    "breadth",
    "canslim",
    "core-satellite",
    "episodic-pivot",
    "expectancy",
    "ftd",
    "mae",
    "mfe",
    "pead",
    "r-multiple",
    "vcp",
}


@dataclass(frozen=True)
class GlossaryTerm:
    heading: str
    term_id: str
    definition: str
    used_by: str


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frontmatter(path: Path) -> dict[str, object]:
    text = _read(path)
    match = re.match(r"\A---\n(?P<yaml>.*?)\n---\n", text, re.DOTALL)
    assert match is not None, f"{path} is missing YAML frontmatter"
    parsed = yaml.safe_load(match.group("yaml"))
    assert isinstance(parsed, dict)
    return parsed


def _terms(path: Path) -> list[GlossaryTerm]:
    return [GlossaryTerm(**match.groupdict()) for match in TERM_PATTERN.finditer(_read(path))]


def test_glossaries_have_matching_complete_term_structure() -> None:
    texts = {lang: _read(path) for lang, path in GLOSSARY_PATHS.items()}
    terms = {lang: _terms(path) for lang, path in GLOSSARY_PATHS.items()}

    assert "## Terms" in texts["en"]
    assert "## 用語一覧" in texts["ja"]
    assert len(terms["en"]) >= 30
    assert [term.term_id for term in terms["en"]] == [term.term_id for term in terms["ja"]]

    for lang, language_terms in terms.items():
        term_ids = [term.term_id for term in language_terms]
        heading_count = len(re.findall(r"^### ", texts[lang], re.MULTILINE))
        assert heading_count == len(language_terms), f"{lang} has a malformed glossary term"
        assert len(term_ids) == len(set(term_ids)), f"duplicate {lang} term ID"
        assert REQUIRED_TERM_IDS <= set(term_ids), f"{lang} is missing a required beginner term"
        for term in language_terms:
            assert len(term.definition.strip()) >= 30, (
                f"{lang}:{term.term_id} needs a plain-language definition"
            )


def test_each_term_links_to_matching_existing_skill_guides() -> None:
    terms = {lang: _terms(path) for lang, path in GLOSSARY_PATHS.items()}
    by_id = {
        lang: {term.term_id: term for term in language_terms}
        for lang, language_terms in terms.items()
    }

    for term_id in by_id["en"]:
        slugs_by_lang: dict[str, set[str]] = {}
        for lang in ("en", "ja"):
            used_by = by_id[lang][term_id].used_by
            links = list(SKILL_LINK_PATTERN.finditer(used_by))
            assert links, f"{lang}:{term_id} needs at least one skill link"
            assert len(links) == used_by.count("]("), (
                f"{lang}:{term_id} contains a non-canonical skill link"
            )

            slugs_by_lang[lang] = set()
            for link in links:
                assert link.group("lang") == lang
                slug = link.group("slug")
                slugs_by_lang[lang].add(slug)
                assert (PROJECT_ROOT / "docs" / lang / "skills" / f"{slug}.md").is_file(), (
                    f"{lang}:{term_id} links to missing skill {slug}"
                )

        assert slugs_by_lang["en"] == slugs_by_lang["ja"], (
            f"{term_id} has different EN/JA skill links"
        )


def test_glossary_frontmatter_and_navigation_are_reciprocal() -> None:
    expected = {
        "en": {
            "title": "Glossary",
            "parent": "English",
            "nav_order": 7,
            "lang_peer": "/ja/glossary/",
            "permalink": "/en/glossary/",
        },
        "ja": {
            "title": "用語集",
            "parent": "日本語",
            "nav_order": 7,
            "lang_peer": "/en/glossary/",
            "permalink": "/ja/glossary/",
        },
    }
    for lang, path in GLOSSARY_PATHS.items():
        frontmatter = _frontmatter(path)
        for key, value in expected[lang].items():
            assert frontmatter[key] == value

        playbooks = _frontmatter(PROJECT_ROOT / "docs" / lang / "playbooks" / "index.md")
        assert playbooks["nav_order"] == 9


def test_beginner_pages_link_to_the_localized_glossary() -> None:
    for lang in ("en", "ja"):
        expected_link = f"{{{{ '/{lang}/glossary/' | relative_url }}}}"
        for filename in ("getting-started.md", "find-your-workflow.md"):
            page = PROJECT_ROOT / "docs" / lang / filename
            assert expected_link in _read(page), f"{page} does not link to the localized glossary"
