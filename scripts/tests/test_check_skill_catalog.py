"""Tests for the localized website skill-catalog contract."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from check_skill_catalog import (  # noqa: E402
    CatalogError,
    _split_table_row,
    main,
    validate_catalogs,
)


def _skill(
    skill_id: str,
    display_name: str,
    integrations: list[dict] | None = None,
) -> dict:
    return {
        "id": skill_id,
        "display_name": display_name,
        "category": "meta",
        "status": "production",
        "integrations": integrations or [],
    }


def _api_values(requirement: str | None, locale: str) -> tuple[str, str, str]:
    cells = {
        "en": {
            "required": "Required",
            "recommended": "Recommended",
            "optional": "Optional",
            "not_required": "--",
            None: "--",
        },
        "ja": {
            "required": "必須",
            "recommended": "推奨",
            "optional": "任意",
            "not_required": "-",
            None: "-",
        },
    }
    return cells[locale][requirement], cells[locale][None], cells[locale][None]


def _catalog(locale: str, requirement: str | None = "required") -> str:
    if locale == "en":
        count = "A comprehensive catalog of all 2 Claude Trading Skills."
        category_heading = "## 1. Test Category"
        category_header = "| Skill | Description | API Requirements |"
        category_end = "## Which Skill Should I Use?"
        api_heading = "## API Requirements Matrix"
        api_header = "| Skill | FMP | FINVIZ Elite | Alpaca |"
        weekly_description = r"Workflow \| publication helper"
    else:
        count = "全2個のClaude Trading Skillsを掲載しています。"
        category_heading = "## 1. テストカテゴリ"
        category_header = "| スキル | 説明 | API要件 |"
        category_end = "## どのスキルを使うべき？"
        api_heading = "## API要件マトリクス"
        api_header = "| スキル | FMP | FINVIZ Elite | Alpaca |"
        weekly_description = r"ワークフロー \| 公開補助"
    values = _api_values(requirement, locale)
    return f"""# Catalog

{count}

{category_heading}

{category_header}
|---|---|---|
| **[Alpha Skill]({{{{ '/{locale}/skills/alpha-skill/' | relative_url }}}})** | Alpha description | No API |
| **Beta Skill** | Beta description | No API |
| **Weekly Trade Strategy** | {weekly_description} | No API |

{category_end}

This recommendation table is outside canonical completeness checks.

{api_heading}

{api_header}
|---|---|---|---|
| Alpha Skill | {values[0]} | {values[1]} | {values[2]} |
| Beta Skill | {values[1]} | {values[1]} | {values[2]} |
"""


def _write_project(
    root: Path,
    *,
    requirement: str | None = "required",
    extra_integrations: list[dict] | None = None,
) -> None:
    integrations = list(extra_integrations or [])
    if requirement is not None:
        integrations.append({"id": "fmp", "type": "market_data", "requirement": requirement})
    payload = {
        "schema_version": 1,
        "skills": [
            _skill("alpha-skill", "Alpha Skill", integrations),
            _skill("beta-skill", "Beta Skill"),
        ],
    }
    (root / "skills-index.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )
    for locale in ("en", "ja"):
        path = root / "docs" / locale / "skill-catalog.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_catalog(locale, requirement), encoding="utf-8")


def _replace(root: Path, locale: str, old: str, new: str) -> None:
    path = root / "docs" / locale / "skill-catalog.md"
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


def test_valid_catalog_accepts_liquid_links_plain_rows_and_escaped_pipes(tmp_path: Path) -> None:
    _write_project(tmp_path)
    validate_catalogs(tmp_path)


@pytest.mark.parametrize("requirement", ["required", "recommended", "optional", "not_required"])
def test_all_target_requirement_values_are_validated(tmp_path: Path, requirement: str) -> None:
    _write_project(tmp_path, requirement=requirement)
    validate_catalogs(tmp_path)


def test_missing_target_integration_maps_to_not_required(tmp_path: Path) -> None:
    _write_project(tmp_path, requirement=None)
    validate_catalogs(tmp_path)


def test_non_target_integrations_are_ignored_even_when_duplicate_or_unknown(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        extra_integrations=[
            {"id": "local_calculation", "requirement": "future_value"},
            {"id": "local_calculation", "requirement": "future_value"},
        ],
    )
    validate_catalogs(tmp_path)


@pytest.mark.parametrize(
    ("integrations", "message"),
    [
        (
            [
                {"id": "fmp", "requirement": "required"},
                {"id": "fmp", "requirement": "optional"},
            ],
            "duplicate targeted integration fmp",
        ),
        ([{"id": "fmp", "requirement": "future_value"}], "unknown requirement"),
    ],
)
def test_target_provider_metadata_fails_closed(
    tmp_path: Path, integrations: list[dict], message: str
) -> None:
    _write_project(tmp_path, requirement=None, extra_integrations=integrations)
    with pytest.raises(CatalogError, match=message):
        validate_catalogs(tmp_path)


def test_link_display_name_must_exactly_match_index(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _replace(tmp_path, "en", "[Alpha Skill]", "[alpha skill]")
    with pytest.raises(CatalogError, match="must exactly match"):
        validate_catalogs(tmp_path)


def test_plain_display_name_must_exactly_match_after_resolution(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _replace(tmp_path, "en", "**Beta Skill**", "**beta skill**")
    with pytest.raises(CatalogError, match="must exactly match"):
        validate_catalogs(tmp_path)


def test_wrong_locale_link_is_rejected(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _replace(tmp_path, "ja", "/ja/skills/alpha-skill/", "/en/skills/alpha-skill/")
    with pytest.raises(CatalogError, match="wrong-locale"):
        validate_catalogs(tmp_path)


def test_missing_and_duplicate_skills_are_rejected(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _replace(tmp_path, "en", "| **Beta Skill** | Beta description | No API |\n", "")
    with pytest.raises(CatalogError, match="missing skills: beta-skill"):
        validate_catalogs(tmp_path)

    _write_project(tmp_path)
    duplicate = "| **Beta Skill** | Beta description | No API |\n"
    _replace(tmp_path, "en", duplicate, duplicate + duplicate)
    with pytest.raises(CatalogError, match="duplicate skill"):
        validate_catalogs(tmp_path)


def test_weekly_trade_strategy_has_exact_category_only_contract(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _replace(
        tmp_path,
        "en",
        "| **Weekly Trade Strategy** | Workflow \\| publication helper | No API |\n",
        "",
    )
    with pytest.raises(CatalogError, match="must appear exactly once"):
        validate_catalogs(tmp_path)

    _write_project(tmp_path)
    _replace(
        tmp_path,
        "en",
        "| Beta Skill | -- | -- | -- |",
        "| Beta Skill | -- | -- | -- |\n| Weekly Trade Strategy | -- | -- | -- |",
    )
    with pytest.raises(CatalogError, match="not allowed in the API matrix"):
        validate_catalogs(tmp_path)


def test_advertised_count_is_required_once_and_must_match(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _replace(tmp_path, "en", "all 2 Claude Trading Skills", "all 3 Claude Trading Skills")
    with pytest.raises(CatalogError, match="advertised skill count 3 must be 2"):
        validate_catalogs(tmp_path)

    _write_project(tmp_path)
    path = tmp_path / "docs" / "ja" / "skill-catalog.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n全2個のClaude Trading Skills\n",
        encoding="utf-8",
    )
    with pytest.raises(CatalogError, match="exactly one advertised skill count"):
        validate_catalogs(tmp_path)


def test_normalized_canonical_display_name_collisions_fail_closed(tmp_path: Path) -> None:
    _write_project(tmp_path)
    path = tmp_path / "skills-index.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["skills"].append(_skill("collision", "Ａｌｐｈａ Ｓｋｉｌｌ"))
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(CatalogError, match="normalized canonical display-name collision"):
        validate_catalogs(tmp_path)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("|---|---|---|", "|---|---|", "invalid separator"),
        (
            "| Skill | Description | API Requirements |",
            "| Skill | Description |",
            "expected header",
        ),
        (
            "| **Beta Skill** | Beta description | No API |",
            "| **Beta Skill** | Beta description | No API | extra |",
            "expected 3 columns",
        ),
        (
            "{{ '/en/skills/alpha-skill/' | relative_url }}",
            "{{ '/en/skills/alpha-skill/' | relative_url }",
            "unclosed Liquid",
        ),
        ("[Alpha Skill]", "[Alpha Skill", "unclosed Markdown bracket"),
    ],
)
def test_malformed_category_tables_fail_closed(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    _write_project(tmp_path)
    _replace(tmp_path, "en", old, new)
    with pytest.raises(CatalogError, match=message):
        validate_catalogs(tmp_path)


def test_extra_table_in_category_is_rejected(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _replace(
        tmp_path,
        "en",
        "## Which Skill Should I Use?",
        "| Other | Table | Here |\n|---|---|---|\n| x | y | z |\n\n## Which Skill Should I Use?",
    )
    with pytest.raises(CatalogError, match="expected exactly one table, found 2"):
        validate_catalogs(tmp_path)


@pytest.mark.parametrize(
    ("locale", "old", "new"),
    [
        (
            "en",
            "| **Beta Skill** | Beta description | No API |",
            "**Beta Skill** | Beta description | No API |",
        ),
        (
            "ja",
            "| Beta Skill | - | - | - |",
            "Beta Skill | - | - | - |",
        ),
        (
            "en",
            "| **Beta Skill** | Beta description | No API |",
            "**Beta Skill** | Beta description",
        ),
        (
            "ja",
            "| Beta Skill | - | - | - |",
            "Beta Skill | -",
        ),
    ],
)
def test_pipe_shaped_rows_without_a_leading_pipe_are_rejected(
    tmp_path: Path, locale: str, old: str, new: str
) -> None:
    _write_project(tmp_path)
    _replace(tmp_path, locale, old, new)
    with pytest.raises(CatalogError, match="pipe-shaped row must start"):
        validate_catalogs(tmp_path)


def test_unclosed_markdown_link_in_description_is_rejected(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _replace(tmp_path, "en", "Beta description", "Beta [source](https://example.com")
    with pytest.raises(CatalogError, match="unclosed Markdown link target"):
        validate_catalogs(tmp_path)


def test_non_leading_row_with_unclosed_liquid_is_rejected(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _replace(
        tmp_path,
        "en",
        "| **Beta Skill** | Beta description | No API |",
        "Unknown Catch-All {{ | --",
    )
    with pytest.raises(CatalogError, match="unclosed Liquid expression"):
        validate_catalogs(tmp_path)


def test_recommendation_content_is_outside_completeness_scope(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _replace(
        tmp_path,
        "en",
        "This recommendation table is outside canonical completeness checks.",
        "| Unknown recommendation | Use it |\n|---|---|\n| Mystery Tool | Often |",
    )
    validate_catalogs(tmp_path)


def test_api_value_drift_is_rejected(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _replace(tmp_path, "ja", "| Alpha Skill | 必須 | - | - |", "| Alpha Skill | 任意 | - | - |")
    with pytest.raises(CatalogError, match="API values"):
        validate_catalogs(tmp_path)


def test_splitter_does_not_treat_liquid_or_escaped_pipes_as_columns() -> None:
    row = "| [Alpha]({{ '/en/skills/alpha/' | relative_url }}) | a\\|b | value |"
    assert _split_table_row(row, "test") == [
        "[Alpha]({{ '/en/skills/alpha/' | relative_url }})",
        "a\\|b",
        "value",
    ]


def test_cli_returns_nonzero_for_drift(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_project(tmp_path)
    assert main(["--project-root", str(tmp_path)]) == 0
    _replace(tmp_path, "en", "all 2 Claude Trading Skills", "all 1 Claude Trading Skills")
    assert main(["--project-root", str(tmp_path)]) == 1
    assert "ERROR:" in capsys.readouterr().err
