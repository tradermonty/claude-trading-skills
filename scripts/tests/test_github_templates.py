import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ISSUE_TEMPLATE_DIR = ROOT / ".github" / "ISSUE_TEMPLATE"
PR_TEMPLATE = ROOT / ".github" / "pull_request_template.md"

EXPECTED_FORMS = {
    "bug_report.yml",
    "skill_improvement.yml",
    "workflow_recipe.yml",
    "real_use_pitfall.yml",
}
ALLOWED_BODY_TYPES = {"markdown", "input", "textarea", "dropdown", "checkboxes"}
SAFE_ID = re.compile(r"^[a-z][a-z0-9-]*$")


def load_yaml(path: Path) -> object:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_expected_issue_template_files_exist() -> None:
    assert (ISSUE_TEMPLATE_DIR / "config.yml").is_file()
    for filename in EXPECTED_FORMS:
        assert (ISSUE_TEMPLATE_DIR / filename).is_file()


def test_issue_template_config_contact_links_render_in_chooser() -> None:
    config = load_yaml(ISSUE_TEMPLATE_DIR / "config.yml")

    assert isinstance(config, dict)
    assert config.get("blank_issues_enabled") is False
    contact_links = config.get("contact_links")
    assert isinstance(contact_links, list)
    assert contact_links

    for link in contact_links:
        assert isinstance(link, dict)
        assert isinstance(link.get("name"), str)
        assert link["name"].strip()
        assert isinstance(link.get("url"), str)
        assert link["url"].startswith("https://")
        assert isinstance(link.get("about"), str)
        assert link["about"].strip()


def test_issue_forms_have_renderable_structure() -> None:
    for filename in EXPECTED_FORMS:
        form = load_yaml(ISSUE_TEMPLATE_DIR / filename)

        assert isinstance(form, dict), filename
        for key in ("name", "description", "title", "body"):
            assert isinstance(form.get(key), str if key != "body" else list), (filename, key)
        assert form["body"], filename

        ids: set[str] = set()
        for index, item in enumerate(form["body"]):
            assert isinstance(item, dict), (filename, index)
            item_type = item.get("type")
            assert item_type in ALLOWED_BODY_TYPES, (filename, index, item_type)

            attributes = item.get("attributes")
            assert isinstance(attributes, dict), (filename, index)

            if item_type == "markdown":
                assert isinstance(attributes.get("value"), str), (filename, index)
                continue

            item_id = item.get("id")
            assert isinstance(item_id, str), (filename, index)
            assert SAFE_ID.match(item_id), (filename, item_id)
            assert item_id not in ids, (filename, item_id)
            ids.add(item_id)

            assert isinstance(attributes.get("label"), str), (filename, item_id)
            assert attributes["label"].strip(), (filename, item_id)

            validations = item.get("validations")
            if validations is not None:
                assert isinstance(validations, dict), (filename, item_id)
                if "required" in validations:
                    assert isinstance(validations["required"], bool), (filename, item_id)

            if item_type == "dropdown":
                options = attributes.get("options")
                assert isinstance(options, list), (filename, item_id)
                assert options, (filename, item_id)
                assert all(isinstance(option, str) and option.strip() for option in options)

            if item_type == "checkboxes":
                assert "validations" not in item, (filename, item_id)
                options = attributes.get("options")
                assert isinstance(options, list), (filename, item_id)
                assert options, (filename, item_id)
                for option in options:
                    assert isinstance(option, dict), (filename, item_id)
                    assert isinstance(option.get("label"), str), (filename, item_id)
                    assert option["label"].strip(), (filename, item_id)
                    assert option.get("required") is True, (filename, item_id)


def test_pull_request_template_matches_repository_gates() -> None:
    template = PR_TEMPLATE.read_text(encoding="utf-8")

    required_phrases = [
        "financial advice",
        "buy/sell signals",
        "secrets",
        "personal information",
        "Targeted pytest",
        "ruff check",
        "ruff format --check",
        "codespell",
        "detect-secrets",
        "Bandit",
        "pre-commit run --files",
        "git diff --check",
        "EN and JA skill docs",
        ".skill",
        "skills-index.yaml",
        "workflows/",
        "skillsets/",
        "generate_catalog_from_index.py --check",
        "金融助言",
        "個人情報",
        "対象テスト",
    ]

    for phrase in required_phrases:
        assert phrase in template
