"""Offline API metadata/source/profile contracts (Issue #653)."""

from __future__ import annotations

import importlib.util
import json
import runpy
import socket
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def checker():
    spec = importlib.util.spec_from_file_location(
        "api_requirements", ROOT / "scripts/check_api_requirements.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project(tmp_path, source, integrations=None):
    scripts = tmp_path / "skills/example/scripts"
    scripts.mkdir(parents=True)
    (scripts / "main.py").write_text(source)
    (tmp_path / "skills-index.yaml").write_text(
        yaml.safe_dump(
            {
                "skills": [
                    {"id": "example", "status": "production", "integrations": integrations or []}
                ]
            }
        )
    )
    return scripts


@pytest.mark.parametrize(
    "source",
    [
        'import os\nx=os.getenv("FMP_API_KEY")',
        'import os as system\nx=system.environ.get("FMP_API_KEY")',
        'from os import getenv as read\nx=read("FMP_API_KEY")',
        'from os import environ as env\nx=env["FMP_API_KEY"]',
        'from os import environ\nx=environ.get("FMP_API_KEY")',
    ],
)
def test_literal_environment_reads_require_provider(tmp_path, source):
    project(tmp_path, source)
    errors = checker().check(tmp_path)
    assert any("API001" in e and "fmp" in e and "main.py:2" in e for e in errors)


@pytest.mark.parametrize(
    "key,provider",
    [
        ("FINVIZ_API_KEY", "finviz"),
        ("ALPACA_API_KEY", "alpaca"),
        ("ALPACA_SECRET_KEY", "alpaca"),
        ("APCA_API_KEY_ID", "alpaca"),
        ("APCA_API_SECRET_KEY", "alpaca"),
    ],
)
def test_other_paid_credentials(tmp_path, key, provider):
    project(tmp_path, f"import os\nx=os.environ.get({key!r})")
    assert any(provider in e for e in checker().check(tmp_path))


def test_documentation_constants_and_noncredential_config_are_not_reads(tmp_path):
    project(
        tmp_path,
        '''import os
"""FMP_API_KEY, FINVIZ_API_KEY"""
pattern = "ALPACA_API_KEY"
x = os.environ.get("ALPACA_PAPER")
''',
    )
    assert checker().check(tmp_path) == []


@pytest.mark.parametrize(
    "requirement", ["required", "recommended", "optional", "not_required", "unknown"]
)
def test_declared_provider_contract(tmp_path, requirement):
    project(
        tmp_path,
        'import os\nx=os.getenv("FMP_API_KEY")',
        [{"id": "fmp", "requirement": requirement}],
    )
    assert bool(checker().check(tmp_path)) == (requirement in ["not_required", "unknown"])


def test_nested_vendored_read_is_checked_but_tests_are_excluded(tmp_path):
    scripts = project(tmp_path, "pass")
    for sub in ("tests/test_fake.py", "test_fake.py"):
        p = scripts / sub
        p.parent.mkdir(exist_ok=True)
        p.write_text('import os\nos.getenv("FMP_API_KEY")')
    assert checker().check(tmp_path) == []
    p = scripts / "vendor/client.py"
    p.parent.mkdir()
    p.write_text('import os\nos.getenv("FMP_API_KEY")')
    assert any("vendor/client.py:2" in e for e in checker().check(tmp_path))


def test_syntax_error_is_a_failure(tmp_path):
    project(tmp_path, "def broken(")
    assert any("API003" in e for e in checker().check(tmp_path))


@pytest.mark.parametrize("optional", [False, True])
def test_no_api_profile_rejects_even_optional_paid_step(tmp_path, optional):
    project(tmp_path, "pass", [{"id": "fmp", "requirement": "required"}])
    (tmp_path / "workflows").mkdir()
    p = tmp_path / "workflows/flow.yaml"
    w = {
        "id": "flow",
        "api_profile": "no-api-basic",
        "steps": [{"step": 1, "skill": "example", "optional": optional}],
    }
    p.write_text(yaml.safe_dump(w))
    assert any("API002" in e for e in checker().check(tmp_path))
    w["api_profile"] = "mixed"
    p.write_text(yaml.safe_dump(w))
    assert checker().check(tmp_path) == []


def test_real_metadata_matches_all_credential_readers():
    assert checker().check(ROOT) == []


@pytest.mark.parametrize(
    "skill,filename",
    [
        ("market-top-detector", "market_top_detector.py"),
        ("downtrend-duration-analyzer", "analyze_downtrends.py"),
    ],
)
def test_required_cli_missing_key_matches_metadata_without_network(
    tmp_path, monkeypatch, capsys, skill, filename
):
    index = yaml.safe_load((ROOT / "skills-index.yaml").read_text())
    entry = next(s for s in index["skills"] if s["id"] == skill)
    assert any(i["id"] == "fmp" and i["requirement"] == "required" for i in entry["integrations"])
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    blocked = Mock(side_effect=AssertionError("network forbidden"))
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    script = ROOT / "skills" / skill / "scripts" / filename
    monkeypatch.syspath_prepend(str(script.parent))
    # Imported sibling names are shared across skill scripts; isolate this CLI.
    for name in ("fmp_client", "utils", "calculators", "report_generator"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys, "argv", [str(script), "--output-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(script), run_name="__main__")
    assert exc.value.code == 1
    assert "FMP" in capsys.readouterr().err
    blocked.assert_not_called()


def test_optional_postmortem_cli_without_key_is_offline(tmp_path, monkeypatch):
    entry = next(
        s
        for s in yaml.safe_load((ROOT / "skills-index.yaml").read_text())["skills"]
        if s["id"] == "signal-postmortem"
    )
    assert any(i["id"] == "fmp" and i["requirement"] == "optional" for i in entry["integrations"])
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    blocked = Mock(side_effect=AssertionError("network forbidden"))
    monkeypatch.setattr(socket.socket, "connect", blocked)
    signals_file = tmp_path / "signals.json"
    signals_file.write_text(
        json.dumps(
            {
                "signals": [
                    {
                        "signal_id": "manual_AAPL_2026-01-01",
                        "ticker": "AAPL",
                        "signal_date": "2026-01-01",
                        "source_skill": "offline-fixture",
                        "predicted_direction": "LONG",
                        "entry_price": 100.0,
                    }
                ]
            }
        )
    )
    script = ROOT / "skills/signal-postmortem/scripts/postmortem_recorder.py"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(script),
            "--signals-file",
            str(signals_file),
            "--signal-id",
            "manual_AAPL_2026-01-01",
            "--exit-price",
            "101",
            "--exit-date",
            "2026-01-10",
            "--output-dir",
            str(tmp_path),
        ],
    )
    runpy.run_path(str(script), run_name="__main__")
    records = list((tmp_path / "postmortems").glob("*.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text())
    assert record["ticker"] == "AAPL"
    assert record["entry_price"] == 100
    assert record["holding_days"] == 9
    assert record["outcome_category"] == "TRUE_POSITIVE"
    assert record["realized_returns"]["actual"] == pytest.approx(0.01)
    assert "5d" not in record["realized_returns"]
    blocked.assert_not_called()


def test_gate_is_wired_to_precommit_and_ci():
    hooks = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
    hook = next(
        h for repo in hooks["repos"] for h in repo["hooks"] if h["id"] == "api-requirements"
    )
    assert hook["entry"] == "python3 scripts/check_api_requirements.py"
    assert hook["always_run"] is True and hook["pass_filenames"] is False
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    assert any(
        step.get("run") == "python3 scripts/check_api_requirements.py"
        for job in ci["jobs"].values()
        for step in job.get("steps", [])
    )


def test_market_regime_mixed_profile_retains_key_free_base():
    workflow = yaml.safe_load((ROOT / "workflows/market-regime-daily.yaml").read_text())
    entries = {
        s["id"]: s for s in yaml.safe_load((ROOT / "skills-index.yaml").read_text())["skills"]
    }
    assert workflow["api_profile"] == "mixed"
    assert workflow["required_skills"] == [
        "market-breadth-analyzer",
        "uptrend-analyzer",
        "exposure-coach",
    ]
    for sid in workflow["required_skills"]:
        assert not any(
            i["id"] in {"fmp", "finviz", "alpaca"} and i["requirement"] == "required"
            for i in entries[sid]["integrations"]
        )
    top = next(s for s in workflow["steps"] if s["skill"] == "market-top-detector")
    assert top["step"] == 3 and top["optional"] is True and top["produces"] == ["top_risk_report"]
    assert "FMP" in top["name"] and "FMP" in top["name_ja"]


def test_market_regime_skillset_matches_mixed_workflow_without_paid_base():
    workflow = yaml.safe_load((ROOT / "workflows/market-regime-daily.yaml").read_text())
    skillset = yaml.safe_load((ROOT / "skillsets/market-regime.yaml").read_text())
    assert skillset["api_profile"] == workflow["api_profile"] == "mixed"
    assert skillset["required_skills"] == workflow["required_skills"]
    assert "market-top-detector" in skillset["recommended_skills"]
    assert "downtrend-duration-analyzer" in skillset["optional_skills"]


def _skill_docs_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_skill_docs_for_api_test", ROOT / "scripts/generate_skill_docs.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Reuses the generator's private ownership helpers (HAND_WRITTEN,
# _doc_is_generated) so this test can never disagree with the drift gate;
# renaming them in generate_skill_docs.py must update this module too.
_SKILL_DOCS = _skill_docs_generator()


def _page_is_generated(page: Path) -> bool:
    """Same ownership reader the doc generator uses (literal `generated: true`)."""
    return _SKILL_DOCS._doc_is_generated(page) is True


def _fmp_required_skills(root: Path) -> list[str]:
    skills = yaml.safe_load((root / "skills-index.yaml").read_text(encoding="utf-8"))["skills"]
    return [
        entry["id"]
        for entry in skills
        if any(
            i.get("id") == "fmp" and i.get("requirement") == "required"
            for i in entry.get("integrations", [])
        )
    ]


def manual_required_fmp_pages(root: Path, hand_written: frozenset[str]) -> list[tuple[str, str]]:
    """(skill, locale) pairs: FMP required in the index, page maintained by hand.

    Mirrors the doc generator's ownership rule: a page is hand-maintained when
    the skill is in HAND_WRITTEN or the page is not literally `generated: true`.
    Missing pages are reported by test_fmp_required_skills_have_both_pages.
    """
    pairs = []
    for skill in _fmp_required_skills(root):
        for locale in ("en", "ja"):
            page = root / "docs" / locale / "skills" / f"{skill}.md"
            if page.is_file() and (skill in hand_written or not _page_is_generated(page)):
                pairs.append((skill, locale))
    return pairs


def fmp_required_page_problems(text: str, locale: str) -> list[str]:
    expected = "FMP Required" if locale == "en" else "FMP必須"
    problems = []
    if f'<span class="badge badge-api">{expected}</span>' not in text:
        problems.append(f"missing badge {expected!r}")
    contradictions = [
        'badge-free">No API',
        'badge-free">API不要',
        "**API Key:** None required",
        "**APIキー:** 不要",
        # Prose that makes the key optional contradicts a required declaration.
        "API なしでも",
        "APIなしでも",
        "FMP API を使う場合",
        "FMP APIを使う場合",
    ]
    problems += [
        f"contradicts required FMP: {marker!r}" for marker in contradictions if marker in text
    ]
    return problems


MANUAL_REQUIRED_FMP_PAGES = manual_required_fmp_pages(ROOT, _SKILL_DOCS.HAND_WRITTEN)


def missing_fmp_required_pages(root: Path) -> list[str]:
    return [
        f"docs/{locale}/skills/{skill}.md"
        for skill in _fmp_required_skills(root)
        for locale in ("en", "ja")
        if not (root / "docs" / locale / "skills" / f"{skill}.md").is_file()
    ]


def test_fmp_required_skills_have_both_pages():
    assert missing_fmp_required_pages(ROOT) == []


@pytest.mark.parametrize("present", ["en", "ja"])
def test_missing_locale_page_is_reported(tmp_path, present):
    (tmp_path / "skills-index.yaml").write_text(
        yaml.safe_dump(
            {
                "skills": [
                    {
                        "id": "new-fmp-skill",
                        "integrations": [{"id": "fmp", "type": "api", "requirement": "required"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    page = tmp_path / "docs" / present / "skills" / "new-fmp-skill.md"
    page.parent.mkdir(parents=True)
    page.write_text("---\ntitle: New\n---\n", encoding="utf-8")
    other = "ja" if present == "en" else "en"
    assert missing_fmp_required_pages(tmp_path) == [f"docs/{other}/skills/new-fmp-skill.md"]


@pytest.mark.parametrize(
    ("locale", "marker"),
    [
        ("en", '<span class="badge badge-free">No API</span>'),
        ("ja", '<span class="badge badge-free">API不要</span>'),
        ("en", "**API Key:** None required"),
        ("ja", "**APIキー:** 不要"),
        ("ja", "API なしでも使えます"),
        ("ja", "APIなしでも使えます"),
        ("ja", "FMP API を使う場合は"),
        ("ja", "FMP APIを使う場合は"),
    ],
)
def test_each_contradicting_marker_is_reported(locale, marker):
    badge = "FMP Required" if locale == "en" else "FMP必須"
    text = f'<span class="badge badge-api">{badge}</span>\n\n{marker}\n'
    problems = fmp_required_page_problems(text, locale)
    assert len(problems) == 1 and problems[0].startswith("contradicts required FMP")


def test_ja_page_without_ja_badge_is_reported():
    assert fmp_required_page_problems(
        '<span class="badge badge-api">FMP Required</span>', "ja"
    ) == ["missing badge 'FMP必須'"]


def test_manual_required_fmp_page_list_is_derived_from_index():
    assert len(MANUAL_REQUIRED_FMP_PAGES) >= 4
    for pair in [
        ("market-top-detector", "en"),
        ("market-top-detector", "ja"),
        ("downtrend-duration-analyzer", "en"),
        ("downtrend-duration-analyzer", "ja"),
    ]:
        assert pair in MANUAL_REQUIRED_FMP_PAGES


@pytest.mark.parametrize(
    ("skill", "locale"),
    MANUAL_REQUIRED_FMP_PAGES,
    ids=[f"{skill}-{locale}" for skill, locale in MANUAL_REQUIRED_FMP_PAGES],
)
def test_manual_required_fmp_skill_guides_match_declarations(skill, locale):
    """Manual pages are outside the doc generator; keep them in line with the index."""
    text = (ROOT / "docs" / locale / "skills" / f"{skill}.md").read_text(encoding="utf-8")
    assert fmp_required_page_problems(text, locale) == []


def _fixture_repo(tmp_path, page_text, *, generated=None, requirement="required"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "skills-index.yaml").write_text(
        yaml.safe_dump(
            {
                "skills": [
                    {
                        "id": "new-fmp-skill",
                        "integrations": [{"id": "fmp", "type": "api", "requirement": requirement}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    page = tmp_path / "docs/en/skills/new-fmp-skill.md"
    page.parent.mkdir(parents=True)
    front = "---\ntitle: New\n" + (f"generated: {generated}\n" if generated is not None else "")
    page.write_text(front + "---\n\n" + page_text, encoding="utf-8")
    return tmp_path


def test_new_hand_written_no_api_page_for_fmp_required_skill_is_caught(tmp_path):
    root = _fixture_repo(tmp_path, '<span class="badge badge-free">No API</span>\n')
    pairs = manual_required_fmp_pages(root, frozenset())
    assert pairs == [("new-fmp-skill", "en")]
    text = (root / "docs/en/skills/new-fmp-skill.md").read_text(encoding="utf-8")
    problems = fmp_required_page_problems(text, "en")
    assert "missing badge 'FMP Required'" in problems
    assert any("No API" in p for p in problems)


def test_optional_key_prose_on_hand_written_page_is_caught(tmp_path):
    root = _fixture_repo(
        tmp_path,
        '<span class="badge badge-api">FMP Required</span>\n\n**API Key:** None required\n',
    )
    assert manual_required_fmp_pages(root, frozenset()) == [("new-fmp-skill", "en")]
    text = (root / "docs/en/skills/new-fmp-skill.md").read_text(encoding="utf-8")
    assert fmp_required_page_problems(text, "en") == [
        "contradicts required FMP: '**API Key:** None required'"
    ]


def test_generated_pages_and_optional_fmp_skills_are_not_collected(tmp_path):
    generated = _fixture_repo(tmp_path / "a", "No badge here\n", generated="true")
    assert manual_required_fmp_pages(generated, frozenset()) == []
    # HAND_WRITTEN wins over a stale generated marker, like the doc generator.
    assert manual_required_fmp_pages(generated, frozenset({"new-fmp-skill"})) == [
        ("new-fmp-skill", "en")
    ]
    optional = _fixture_repo(tmp_path / "b", "No badge here\n", requirement="optional")
    assert manual_required_fmp_pages(optional, frozenset()) == []


@pytest.mark.parametrize(
    ("frontmatter", "body", "expected"),
    [
        ("generated: true\n", "", True),
        ("generated: false\n", "", False),
        ("title: x\n", "generated: true in prose\n", False),
        # The generator treats anything but a literal `true` as hand-maintained.
        ("generated: True\n", "", False),
        # A title with an unquoted colon must not break collection.
        ("title: Guide: part one\ngenerated: true\n", "", True),
    ],
)
def test_generated_marker_matches_the_doc_generator(tmp_path, frontmatter, body, expected):
    page = tmp_path / "page.md"
    page.write_text(f"---\n{frontmatter}---\n\n{body}", encoding="utf-8")
    assert _page_is_generated(page) is expected
