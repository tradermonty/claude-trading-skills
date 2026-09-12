#!/usr/bin/env python3
"""Validate website skill catalogs against ``skills-index.yaml``.

The website catalogs are intentionally hand-written and localized, so this
checker validates their canonical skill identity and API requirement fields
without rewriting descriptions or recommendations.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TARGET_PROVIDERS = ("fmp", "finviz", "alpaca")
VALID_REQUIREMENTS = {"required", "recommended", "optional", "not_required"}
WEEKLY_TRADE_STRATEGY = "Weekly Trade Strategy"


class CatalogError(ValueError):
    """Raised when a website catalog violates the canonical contract."""


@dataclass(frozen=True)
class LocaleSpec:
    locale: str
    path: str
    category_end: str
    api_heading: str
    category_header: tuple[str, str, str]
    api_header: tuple[str, str, str, str]
    count_pattern: re.Pattern[str]
    api_values: dict[str, str]
    missing_api_value: str


LOCALES = (
    LocaleSpec(
        locale="en",
        path="docs/en/skill-catalog.md",
        category_end="## Which Skill Should I Use?",
        api_heading="## API Requirements Matrix",
        category_header=("Skill", "Description", "API Requirements"),
        api_header=("Skill", "FMP", "FINVIZ Elite", "Alpaca"),
        count_pattern=re.compile(r"\ball\s+(\d+)\s+Claude Trading Skills\b"),
        api_values={
            "required": "Required",
            "recommended": "Recommended",
            "optional": "Optional",
            "not_required": "--",
        },
        missing_api_value="--",
    ),
    LocaleSpec(
        locale="ja",
        path="docs/ja/skill-catalog.md",
        category_end="## どのスキルを使うべき？",
        api_heading="## API要件マトリクス",
        category_header=("スキル", "説明", "API要件"),
        api_header=("スキル", "FMP", "FINVIZ Elite", "Alpaca"),
        count_pattern=re.compile(r"全\s*(\d+)\s*個のClaude Trading Skills"),
        api_values={
            "required": "必須",
            "recommended": "推奨",
            "optional": "任意",
            "not_required": "-",
        },
        missing_api_value="-",
    ),
)


@dataclass(frozen=True)
class Skill:
    skill_id: str
    display_name: str
    requirements: dict[str, str]


def _normalized_name(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _load_skills(index_path: Path) -> tuple[dict[str, Skill], dict[str, Skill]]:
    try:
        payload = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CatalogError(f"cannot read {index_path}: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("skills"), list):
        raise CatalogError("skills-index.yaml must contain a skills list")

    by_id: dict[str, Skill] = {}
    by_name: dict[str, Skill] = {}
    for position, raw_skill in enumerate(payload["skills"]):
        if not isinstance(raw_skill, dict):
            raise CatalogError(f"skills[{position}] must be a mapping")
        if raw_skill.get("status") == "deprecated":
            continue
        skill_id = raw_skill.get("id")
        display_name = raw_skill.get("display_name")
        if not isinstance(skill_id, str) or not skill_id:
            raise CatalogError(f"skills[{position}].id must be a non-empty string")
        if not isinstance(display_name, str) or not display_name:
            raise CatalogError(f"skills[{position}].display_name must be a non-empty string")

        requirements: dict[str, str] = {}
        integrations = raw_skill.get("integrations") or []
        if not isinstance(integrations, list):
            raise CatalogError(f"{skill_id}: integrations must be a list")
        for integration in integrations:
            if not isinstance(integration, dict):
                raise CatalogError(f"{skill_id}: integration entries must be mappings")
            provider = integration.get("id")
            if provider not in TARGET_PROVIDERS:
                continue
            if provider in requirements:
                raise CatalogError(f"{skill_id}: duplicate targeted integration {provider}")
            requirement = integration.get("requirement")
            if not isinstance(requirement, str) or requirement not in VALID_REQUIREMENTS:
                raise CatalogError(
                    f"{skill_id}: unknown requirement {requirement!r} for {provider}"
                )
            requirements[provider] = requirement

        skill = Skill(skill_id, display_name, requirements)
        if skill_id in by_id:
            raise CatalogError(f"duplicate canonical skill id: {skill_id}")
        normalized = _normalized_name(display_name)
        if normalized in by_name:
            other = by_name[normalized]
            raise CatalogError(
                "normalized canonical display-name collision: "
                f"{other.display_name!r} and {display_name!r}"
            )
        by_id[skill_id] = skill
        by_name[normalized] = skill
    return by_id, by_name


def _split_table_row(line: str, context: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        raise CatalogError(f"{context}: malformed Markdown table row")

    cells: list[str] = []
    current: list[str] = []
    liquid_depth = 0
    index = 1
    end = len(stripped) - 1
    while index < end:
        pair = stripped[index : index + 2]
        if pair == "{{":
            if liquid_depth:
                raise CatalogError(f"{context}: nested Liquid expression")
            liquid_depth = 1
            current.append(pair)
            index += 2
            continue
        if pair == "}}":
            if not liquid_depth:
                raise CatalogError(f"{context}: unmatched Liquid closer")
            liquid_depth = 0
            current.append(pair)
            index += 2
            continue
        char = stripped[index]
        if char == "\\":
            if index + 1 >= end:
                raise CatalogError(f"{context}: dangling Markdown escape")
            current.extend((char, stripped[index + 1]))
            index += 2
            continue
        if char == "|" and not liquid_depth:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    if liquid_depth:
        raise CatalogError(f"{context}: unclosed Liquid expression")
    cells.append("".join(current).strip())
    return cells


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _outside_pipe_count(line: str, context: str) -> int:
    """Count unescaped pipes that are not inside a Liquid expression."""
    count = 0
    liquid_depth = 0
    index = 0
    while index < len(line):
        pair = line[index : index + 2]
        if pair == "{{":
            if liquid_depth:
                raise CatalogError(f"{context}: nested Liquid expression")
            liquid_depth += 1
            index += 2
            continue
        if pair == "}}":
            if not liquid_depth:
                raise CatalogError(f"{context}: unmatched Liquid closer")
            liquid_depth -= 1
            index += 2
            continue
        if line[index] == "\\":
            index += 2
            continue
        if line[index] == "|" and not liquid_depth:
            count += 1
        index += 1
    if liquid_depth:
        raise CatalogError(f"{context}: unclosed Liquid expression")
    return count


def _validate_cell_markup(cell: str, context: str) -> None:
    """Reject unbalanced brackets and unfinished Markdown link targets."""
    bracket_depth = 0
    index = 0
    while index < len(cell):
        if cell[index] == "\\":
            index += 2
            continue
        if cell[index] == "[":
            bracket_depth += 1
        elif cell[index] == "]":
            bracket_depth -= 1
            if bracket_depth < 0:
                raise CatalogError(f"{context}: unmatched Markdown bracket")
        index += 1
    if bracket_depth:
        raise CatalogError(f"{context}: unclosed Markdown bracket")

    for match in re.finditer(r"\]\(", cell):
        parenthesis_depth = 1
        index = match.end()
        while index < len(cell) and parenthesis_depth:
            if cell[index] == "\\":
                index += 2
                continue
            if cell[index] == "(":
                parenthesis_depth += 1
            elif cell[index] == ")":
                parenthesis_depth -= 1
            index += 1
        if parenthesis_depth:
            raise CatalogError(f"{context}: unclosed Markdown link target")


def _table_blocks(lines: list[str], start: int, end: int) -> list[tuple[int, list[str]]]:
    blocks: list[tuple[int, list[str]]] = []
    cursor = start
    while cursor < end:
        if not lines[cursor].lstrip().startswith("|"):
            cursor += 1
            continue
        first = cursor
        block: list[str] = []
        while cursor < end and lines[cursor].lstrip().startswith("|"):
            block.append(lines[cursor])
            cursor += 1
        blocks.append((first, block))
    return blocks


def _parse_one_table(
    lines: list[str],
    start: int,
    end: int,
    expected_header: tuple[str, ...],
    context: str,
) -> list[list[str]]:
    for line_number in range(start, end):
        line = lines[line_number]
        line_context = f"{context} line {line_number + 1}"
        if not line.lstrip().startswith("|") and _outside_pipe_count(line, line_context) >= 1:
            raise CatalogError(f"{line_context}: pipe-shaped row must start with '|'")
    blocks = _table_blocks(lines, start, end)
    if len(blocks) != 1:
        raise CatalogError(f"{context}: expected exactly one table, found {len(blocks)}")
    first_line, block = blocks[0]
    if len(block) < 3:
        raise CatalogError(f"{context}: table must include header, separator, and data")
    parsed = [
        _split_table_row(line, f"{context} line {first_line + offset + 1}")
        for offset, line in enumerate(block)
    ]
    for row_offset, row in enumerate(parsed):
        for column, cell in enumerate(row, start=1):
            _validate_cell_markup(
                cell,
                f"{context} line {first_line + row_offset + 1} column {column}",
            )
    if tuple(parsed[0]) != expected_header:
        raise CatalogError(
            f"{context}: expected header {expected_header!r}, found {tuple(parsed[0])!r}"
        )
    if len(parsed[1]) != len(expected_header) or not _is_separator(parsed[1]):
        raise CatalogError(f"{context}: invalid separator row")
    for row_number, row in enumerate(parsed[2:], start=first_line + 3):
        if len(row) != len(expected_header):
            raise CatalogError(
                f"{context} line {row_number}: expected {len(expected_header)} columns, "
                f"found {len(row)}"
            )
        if _is_separator(row):
            raise CatalogError(f"{context} line {row_number}: extra separator row")
    return parsed[2:]


def _unique_line(lines: list[str], exact: str, context: str) -> int:
    matches = [index for index, line in enumerate(lines) if line == exact]
    if len(matches) != 1:
        raise CatalogError(f"{context}: expected one {exact!r} heading, found {len(matches)}")
    return matches[0]


def _link_target_id(target: str, locale: str, context: str) -> str:
    match = re.fullmatch(
        rf"\{{\{{\s*(['\"])/{locale}/skills/([a-z0-9-]+)/\1\s*\|\s*relative_url\s*\}}\}}",
        target,
    )
    if not match:
        raise CatalogError(f"{context}: invalid or wrong-locale skill link {target!r}")
    return match.group(2)


def _identity(
    cell: str,
    locale: str,
    by_id: dict[str, Skill],
    by_name: dict[str, Skill],
    context: str,
) -> Skill | None:
    value = cell.strip()
    if value.startswith("**") or value.endswith("**"):
        if not (value.startswith("**") and value.endswith("**") and len(value) > 4):
            raise CatalogError(f"{context}: unbalanced bold markup")
        value = value[2:-2].strip()

    if "[" in value or "](" in value:
        match = re.fullmatch(r"\[([^\]]+)\]\((.+)\)", value)
        if not match:
            raise CatalogError(f"{context}: unclosed or malformed Markdown link")
        visible, target = match.groups()
        skill_id = _link_target_id(target, locale, context)
        skill = by_id.get(skill_id)
        if skill is None:
            raise CatalogError(f"{context}: unknown skill id {skill_id!r}")
    else:
        visible = value
        if visible == WEEKLY_TRADE_STRATEGY:
            return None
        skill = by_name.get(_normalized_name(visible))
        if skill is None:
            raise CatalogError(f"{context}: unknown skill display name {visible!r}")

    if visible != skill.display_name:
        raise CatalogError(
            f"{context}: display name {visible!r} must exactly match {skill.display_name!r}"
        )
    return skill


def _record_skill(seen: dict[str, str], skill: Skill, context: str, section_name: str) -> None:
    previous = seen.get(skill.skill_id)
    if previous is not None:
        raise CatalogError(
            f"{context}: duplicate skill {skill.display_name!r}; first seen in {previous}"
        )
    seen[skill.skill_id] = section_name


def _validate_category_tables(
    lines: list[str],
    spec: LocaleSpec,
    by_id: dict[str, Skill],
    by_name: dict[str, Skill],
) -> None:
    start_matches = [i for i, line in enumerate(lines) if re.fullmatch(r"## 1\. .+", line)]
    if len(start_matches) != 1:
        raise CatalogError(
            f"{spec.locale} categories: expected one numbered category 1 heading, "
            f"found {len(start_matches)}"
        )
    start = start_matches[0]
    end = _unique_line(lines, spec.category_end, f"{spec.locale} categories")
    if end <= start:
        raise CatalogError(f"{spec.locale} categories: invalid section boundaries")

    headings = [index for index in range(start, end) if lines[index].startswith("## ")]
    if not headings or any(not re.fullmatch(r"## \d+\. .+", lines[i]) for i in headings):
        raise CatalogError(f"{spec.locale} categories: invalid category heading")

    seen: dict[str, str] = {}
    weekly_count = 0
    for position, heading in enumerate(headings):
        section_end = headings[position + 1] if position + 1 < len(headings) else end
        heading_text = lines[heading]
        rows = _parse_one_table(
            lines,
            heading + 1,
            section_end,
            spec.category_header,
            f"{spec.locale} category {heading_text!r}",
        )
        for row_offset, row in enumerate(rows, start=1):
            context = f"{spec.locale} category {heading_text!r} row {row_offset}"
            skill = _identity(row[0], spec.locale, by_id, by_name, context)
            if skill is None:
                weekly_count += 1
            else:
                _record_skill(seen, skill, context, heading_text)

    expected = set(by_id)
    missing = sorted(expected - set(seen))
    if missing:
        raise CatalogError(f"{spec.locale} categories: missing skills: {', '.join(missing)}")
    if weekly_count != 1:
        raise CatalogError(
            f"{spec.locale} categories: {WEEKLY_TRADE_STRATEGY!r} must appear exactly once; "
            f"found {weekly_count}"
        )


def _validate_api_table(
    lines: list[str],
    spec: LocaleSpec,
    by_id: dict[str, Skill],
    by_name: dict[str, Skill],
) -> None:
    heading = _unique_line(lines, spec.api_heading, f"{spec.locale} API matrix")
    following = [
        index for index in range(heading + 1, len(lines)) if lines[index].startswith("## ")
    ]
    end = following[0] if following else len(lines)
    rows = _parse_one_table(
        lines,
        heading + 1,
        end,
        spec.api_header,
        f"{spec.locale} API matrix",
    )

    seen: dict[str, str] = {}
    for row_offset, row in enumerate(rows, start=1):
        context = f"{spec.locale} API matrix row {row_offset}"
        skill = _identity(row[0], spec.locale, by_id, by_name, context)
        if skill is None:
            raise CatalogError(
                f"{context}: {WEEKLY_TRADE_STRATEGY!r} is not allowed in the API matrix"
            )
        _record_skill(seen, skill, context, spec.api_heading)
        expected_values = tuple(
            spec.api_values[skill.requirements.get(provider, "not_required")]
            if provider in skill.requirements
            else spec.missing_api_value
            for provider in TARGET_PROVIDERS
        )
        actual_values = tuple(row[1:])
        if actual_values != expected_values:
            raise CatalogError(
                f"{context}: {skill.display_name} API values {actual_values!r} "
                f"must be {expected_values!r}"
            )

    missing = sorted(set(by_id) - set(seen))
    if missing:
        raise CatalogError(f"{spec.locale} API matrix: missing skills: {', '.join(missing)}")


def _validate_count(text: str, spec: LocaleSpec, canonical_count: int) -> None:
    matches = spec.count_pattern.findall(text)
    if len(matches) != 1:
        raise CatalogError(
            f"{spec.locale}: expected exactly one advertised skill count, found {len(matches)}"
        )
    if int(matches[0]) != canonical_count:
        raise CatalogError(
            f"{spec.locale}: advertised skill count {matches[0]} must be {canonical_count}"
        )


def validate_catalogs(project_root: Path = ROOT) -> None:
    by_id, by_name = _load_skills(project_root / "skills-index.yaml")
    for spec in LOCALES:
        catalog_path = project_root / spec.path
        try:
            text = catalog_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CatalogError(f"cannot read {catalog_path}: {exc}") from exc
        lines = text.splitlines()
        _validate_count(text, spec, len(by_id))
        _validate_category_tables(lines, spec, by_id, by_name)
        _validate_api_table(lines, spec, by_id, by_name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        validate_catalogs(args.project_root.resolve())
    except CatalogError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("OK: website EN/JA skill catalogs match skills-index.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
