import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ISSUE_TEMPLATE_DIR = ROOT / ".github" / "ISSUE_TEMPLATE"
PR_TEMPLATE = ROOT / ".github" / "pull_request_template.md"

EXPECTED_FORM_LABELS = {
    "bug_report.yml": ["bug"],
    "skill_improvement.yml": ["enhancement"],
    "workflow_recipe.yml": ["documentation"],
    "real_use_pitfall.yml": ["documentation"],
}
EXPECTED_CHOOSER_FILES = set(EXPECTED_FORM_LABELS) | {"config.yml"}

FORM_REQUIRED_KEYS = {"name", "description", "title", "labels", "body"}
FORM_ALLOWED_KEYS = FORM_REQUIRED_KEYS | {"assignees"}
BODY_TYPES = {"markdown", "input", "textarea", "dropdown", "checkboxes"}
USER_INPUT_TYPES = BODY_TYPES - {"markdown"}
ITEM_ALLOWED_KEYS = {
    "markdown": {"type", "attributes"},
    "input": {"type", "id", "attributes", "validations"},
    "textarea": {"type", "id", "attributes", "validations"},
    "dropdown": {"type", "id", "attributes", "validations"},
    "checkboxes": {"type", "id", "attributes", "validations"},
}
ATTRIBUTE_ALLOWED_KEYS = {
    "markdown": {"value"},
    "input": {"label", "description", "placeholder", "value"},
    "textarea": {"label", "description", "placeholder", "value", "render"},
    "dropdown": {"label", "description", "multiple", "options"},
    "checkboxes": {"label", "description", "options"},
}
ATTRIBUTE_REQUIRED_KEYS = {
    "markdown": {"value"},
    "input": {"label", "description"},
    "textarea": {"label", "description"},
    "dropdown": {"label", "description", "options"},
    "checkboxes": {"label", "description", "options"},
}
VALIDATION_ALLOWED_KEYS = {"required"}
CHECKBOX_OPTION_ALLOWED_KEYS = {"label", "required"}
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
JAPANESE_TEXT = re.compile(r"[ぁ-んァ-ン一-龯]")

EXPECTED_CONTACT_LINKS = [
    "https://github.com/tradermonty/claude-trading-skills/blob/main/PROJECT_VISION.md",
    "https://tradermonty.github.io/claude-trading-skills/",
]

FMP_PACKAGE_DRIFT_COMMAND = (
    "python3 scripts/package_skills.py --check "
    "--skill pead-screener "
    "--skill earnings-trade-analyzer "
    "--skill ibd-distribution-day-monitor "
    "--skill vcp-screener "
    "--skill parabolic-short-trade-planner "
    "--skill ftd-detector "
    "--skill canslim-screener "
    "--skill macro-regime-detector "
    "--skill market-top-detector"
)


def load_yaml(path: Path) -> object:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def assert_nonblank_string(value: object, context: tuple[object, ...]) -> str:
    assert isinstance(value, str), context
    assert value.strip(), context
    return value


def test_issue_template_directory_has_exact_chooser_files() -> None:
    actual_files = {path.name for path in ISSUE_TEMPLATE_DIR.iterdir() if path.is_file()}
    assert actual_files == EXPECTED_CHOOSER_FILES


def test_issue_template_config_has_exact_contact_links() -> None:
    config = load_yaml(ISSUE_TEMPLATE_DIR / "config.yml")

    assert isinstance(config, dict)
    assert set(config) == {"blank_issues_enabled", "contact_links"}
    assert config["blank_issues_enabled"] is False

    contact_links = config["contact_links"]
    assert isinstance(contact_links, list)
    assert [link.get("url") for link in contact_links] == EXPECTED_CONTACT_LINKS
    for index, link in enumerate(contact_links):
        assert isinstance(link, dict), index
        assert set(link) == {"name", "url", "about"}, index
        for key in ("name", "url", "about"):
            value = assert_nonblank_string(link[key], (index, key))
            if key != "url":
                assert JAPANESE_TEXT.search(value), (index, key)


def test_issue_forms_match_github_schema_invariants() -> None:
    form_names: set[str] = set()

    for filename, expected_labels in EXPECTED_FORM_LABELS.items():
        form = load_yaml(ISSUE_TEMPLATE_DIR / filename)
        assert isinstance(form, dict), filename
        assert FORM_REQUIRED_KEYS <= set(form), filename
        assert set(form) <= FORM_ALLOWED_KEYS, (filename, set(form) - FORM_ALLOWED_KEYS)

        name = assert_nonblank_string(form["name"], (filename, "name"))
        description = assert_nonblank_string(form["description"], (filename, "description"))
        title = assert_nonblank_string(form["title"], (filename, "title"))
        assert len(name) <= 64, filename
        assert len(description) <= 200, filename
        assert len(title) <= 256, filename
        assert JAPANESE_TEXT.search(name), (filename, "name")
        assert JAPANESE_TEXT.search(description), (filename, "description")
        assert name not in form_names, (filename, name)
        form_names.add(name)

        assert form["labels"] == expected_labels, filename
        if "assignees" in form:
            assert isinstance(form["assignees"], list), filename
            assert all(isinstance(value, str) for value in form["assignees"]), filename

        body = form["body"]
        assert isinstance(body, list), filename
        assert body, filename
        assert len(body) <= 10, filename
        assert any(item.get("type") in USER_INPUT_TYPES for item in body), filename

        ids: set[str] = set()
        labels: set[str] = set()
        acknowledgement_options: list[str] | None = None

        for index, item in enumerate(body):
            assert isinstance(item, dict), (filename, index)
            item_type = item.get("type")
            assert item_type in BODY_TYPES, (filename, index, item_type)
            assert set(item) <= ITEM_ALLOWED_KEYS[item_type], (
                filename,
                index,
                set(item) - ITEM_ALLOWED_KEYS[item_type],
            )

            attributes = item.get("attributes")
            assert isinstance(attributes, dict), (filename, index, "attributes")
            assert ATTRIBUTE_REQUIRED_KEYS[item_type] <= set(attributes), (
                filename,
                index,
                "required attributes",
            )
            assert set(attributes) <= ATTRIBUTE_ALLOWED_KEYS[item_type], (
                filename,
                index,
                set(attributes) - ATTRIBUTE_ALLOWED_KEYS[item_type],
            )

            if item_type == "markdown":
                assert_nonblank_string(attributes["value"], (filename, index, "value"))
                continue

            item_id = assert_nonblank_string(item.get("id"), (filename, index, "id"))
            assert SAFE_ID.fullmatch(item_id), (filename, item_id)
            assert item_id not in ids, (filename, item_id)
            ids.add(item_id)

            label = assert_nonblank_string(attributes["label"], (filename, item_id, "label"))
            description_text = assert_nonblank_string(
                attributes["description"], (filename, item_id, "description")
            )
            assert label not in labels, (filename, label)
            labels.add(label)
            assert JAPANESE_TEXT.search(label), (filename, item_id, "label")
            assert JAPANESE_TEXT.search(description_text), (
                filename,
                item_id,
                "description",
            )

            validations = item.get("validations", {})
            assert isinstance(validations, dict), (filename, item_id, "validations")
            assert set(validations) <= VALIDATION_ALLOWED_KEYS, (filename, item_id)
            if "required" in validations:
                assert isinstance(validations["required"], bool), (filename, item_id)

            if item_type not in {"dropdown", "checkboxes"}:
                continue

            options = attributes["options"]
            assert isinstance(options, list), (filename, item_id, "options")
            assert options, (filename, item_id, "options")

            if item_type == "dropdown":
                normalized_options: list[str] = []
                for option in options:
                    option_text = assert_nonblank_string(option, (filename, item_id, "option"))
                    assert option_text.casefold() != "none", (filename, item_id)
                    normalized_options.append(option_text)
                assert len(normalized_options) == len(set(normalized_options)), (
                    filename,
                    item_id,
                    "duplicate options",
                )
                continue

            checkbox_labels: list[str] = []
            for option in options:
                assert isinstance(option, dict), (filename, item_id, "option")
                assert set(option) <= CHECKBOX_OPTION_ALLOWED_KEYS, (
                    filename,
                    item_id,
                    set(option) - CHECKBOX_OPTION_ALLOWED_KEYS,
                )
                option_label = assert_nonblank_string(
                    option.get("label"), (filename, item_id, "option label")
                )
                assert JAPANESE_TEXT.search(option_label), (
                    filename,
                    item_id,
                    "option label",
                )
                assert option.get("required") is True, (filename, item_id)
                checkbox_labels.append(option_label)
            assert len(checkbox_labels) == len(set(checkbox_labels)), (
                filename,
                item_id,
                "duplicate options",
            )
            if item_id == "acknowledgements":
                acknowledgement_options = checkbox_labels

        assert acknowledgement_options is not None, filename
        acknowledgements = " ".join(acknowledgement_options).casefold()
        for phrase in ("secret", "api key", "personal", "financial advice"):
            assert phrase in acknowledgements, (filename, phrase)
        assert "broker execution" in acknowledgements, filename


def test_pull_request_template_matches_local_and_ci_gates() -> None:
    template = PR_TEMPLATE.read_text(encoding="utf-8")

    required_commands = [
        "python3.9 -m pytest",
        "bash scripts/run_all_tests.sh",
        "ruff check skills/ scripts/",
        "ruff format --check skills/ scripts/",
        "codespell --toml pyproject.toml skills/ scripts/",
        "pre-commit run --all-files",
        "git diff --check",
        "python3 scripts/validate_skills_index.py",
        "python3 scripts/validate_skills_index.py --strict-workflows",
        "python3 scripts/validate_skills_index.py --strict-metadata",
        "python3 scripts/validate_skillsets.py",
        "python3 scripts/generate_skill_docs.py --check",
        "python3 scripts/generate_workflow_docs.py --check",
        "python3 scripts/generate_skillset_docs.py --check",
        "python3 scripts/generate_catalog_from_index.py --check",
        "python3 skills/trading-skills-navigator/scripts/build_snapshot.py --check",
        "python3 scripts/generate_fmp_client.py --check",
        "python3 scripts/check_package_drift_for_changed_skills.py",
        FMP_PACKAGE_DRIFT_COMMAND,
    ]
    for command in required_commands:
        assert command in template, command

    required_phrases = [
        "Local validation / ローカル検証",
        "CI and generated-artifact gates / CI・生成物ゲート",
        "N/A",
        "EN and JA",
        ".skill",
        "financial advice",
        "broker execution",
        "secrets",
        "personal information",
        "金融助言",
        "個人情報",
    ]
    for phrase in required_phrases:
        assert phrase in template, phrase
