"""Skillset validator tests — happy path + one failing case per SK code.

Each test builds a minimal repo layout in tmp_path and asserts the validator
emits the specific SK### code. A final test validates the 4 real shipped
manifests against the real repo root (0 errors).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from validate_skillsets import validate  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_index(root: Path, skills: list[dict]) -> None:
    payload = {
        "schema_version": 1,
        "categories": [
            "market-regime",
            "core-portfolio",
            "swing-opportunity",
            "trade-planning",
            "trade-memory",
            "strategy-research",
            "advanced-satellite",
            "meta",
        ],
        "skills": skills,
    }
    (root / "skills-index.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )


def _write_workflow(root: Path, wid: str, content: dict) -> None:
    wf_dir = root / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / f"{wid}.yaml").write_text(
        yaml.safe_dump({"id": wid, **content}, sort_keys=False), encoding="utf-8"
    )


def _write_skillset(root: Path, sid: str, content: dict) -> None:
    ss_dir = root / "skillsets"
    ss_dir.mkdir(parents=True, exist_ok=True)
    (ss_dir / f"{sid}.yaml").write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")


def _skill(sid: str, category: str = "market-regime", **kw: Any) -> dict:
    return {
        "id": sid,
        "display_name": sid,
        "category": category,
        "status": kw.get("status", "production"),
        "summary": "x",
        "integrations": kw.get(
            "integrations",
            [{"id": "local_calculation", "type": "calculation", "requirement": "not_required"}],
        ),
    }


def _base_manifest() -> dict:
    """A fully-valid market-regime manifest (mutated per-test to trip one code)."""
    return {
        "schema_version": 1,
        "id": "market-regime",
        "display_name": "Market Regime",
        "category": "market-regime",
        "timeframe": "daily",
        "difficulty": "beginner",
        "api_profile": "no-api-basic",
        "target_users": ["part-time-swing-trader"],
        "when_to_use": "When deciding daily exposure posture.",
        "when_not_to_use": "Not as a standalone buy/sell signal.",
        "required_skills": ["sk-a", "sk-b"],
        "recommended_skills": ["sk-c"],
        "optional_skills": ["sk-d"],
        "related_workflows": ["market-regime-daily"],
    }


def _scaffold(root: Path, manifest: dict, *, filename: str = "market-regime") -> None:
    """Write a coherent index + workflow + skillset; caller pre-mutates manifest."""
    _write_index(
        root,
        [
            _skill("sk-a"),
            _skill("sk-b"),
            _skill("sk-c"),
            _skill("sk-d"),
        ],
    )
    _write_workflow(
        root,
        "market-regime-daily",
        {"api_profile": "no-api-basic", "required_skills": ["sk-a", "sk-b"]},
    )
    _write_skillset(root, filename, manifest)


def _codes(root: Path) -> set[str]:
    return {f.code for f in validate(root) if f.severity == "error"}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_manifest_passes(tmp_path: Path) -> None:
    _scaffold(tmp_path, _base_manifest())
    assert validate(tmp_path) == []


def test_absent_skillsets_dir_is_ok(tmp_path: Path) -> None:
    assert validate(tmp_path) == []


def test_real_shipped_manifests_validate_clean() -> None:
    repo = Path(__file__).resolve().parents[2]
    findings = [f for f in validate(repo) if f.severity == "error"]
    assert findings == [], [f.format() for f in findings]


# ---------------------------------------------------------------------------
# One failing case per SK code
# ---------------------------------------------------------------------------


def test_sk001_id_ne_filename(tmp_path: Path) -> None:
    m = _base_manifest()
    _scaffold(tmp_path, m, filename="wrong-name")
    assert "SK001" in _codes(tmp_path)


def test_sk002_non_category_id(tmp_path: Path) -> None:
    m = _base_manifest()
    m["id"] = "not-a-category"
    m["category"] = "not-a-category"
    _scaffold(tmp_path, m, filename="not-a-category")
    assert "SK002" in _codes(tmp_path)


def test_sk002_category_ne_id(tmp_path: Path) -> None:
    m = _base_manifest()
    m["category"] = "core-portfolio"
    _scaffold(tmp_path, m)
    assert "SK002" in _codes(tmp_path)


def test_sk003_bad_scalar(tmp_path: Path) -> None:
    m = _base_manifest()
    m["timeframe"] = "hourly"
    _scaffold(tmp_path, m)
    assert "SK003" in _codes(tmp_path)


def test_sk004_blank_when_not_to_use(tmp_path: Path) -> None:
    m = _base_manifest()
    m["when_not_to_use"] = "   "
    _scaffold(tmp_path, m)
    assert "SK004" in _codes(tmp_path)


def test_sk005_empty_required_skills(tmp_path: Path) -> None:
    m = _base_manifest()
    m["required_skills"] = []
    _scaffold(tmp_path, m)
    assert "SK005" in _codes(tmp_path)


def test_sk005_empty_target_users(tmp_path: Path) -> None:
    m = _base_manifest()
    m["target_users"] = []
    _scaffold(tmp_path, m)
    assert "SK005" in _codes(tmp_path)


@pytest.mark.parametrize("field", ["recommended_skills", "optional_skills"])
def test_sk005_missing_recommended_optional_key(tmp_path: Path, field: str) -> None:
    # Dropping the key entirely must error (not be coerced to []).
    m = _base_manifest()
    del m[field]
    _scaffold(tmp_path, m)
    assert "SK005" in _codes(tmp_path)


@pytest.mark.parametrize("field", ["recommended_skills", "optional_skills"])
def test_sk005_empty_list_recommended_optional_ok(tmp_path: Path, field: str) -> None:
    # Present but empty is allowed for recommended/optional.
    m = _base_manifest()
    m[field] = []
    _scaffold(tmp_path, m)
    assert "SK005" not in _codes(tmp_path)


def test_sk006_unknown_skill(tmp_path: Path) -> None:
    m = _base_manifest()
    m["optional_skills"] = ["does-not-exist"]
    _scaffold(tmp_path, m)
    assert "SK006" in _codes(tmp_path)


def test_sk007_deprecated_required(tmp_path: Path) -> None:
    m = _base_manifest()
    _write_index(
        tmp_path,
        [
            _skill("sk-a", status="deprecated"),
            _skill("sk-b"),
            _skill("sk-c"),
            _skill("sk-d"),
        ],
    )
    _write_workflow(
        tmp_path,
        "market-regime-daily",
        {"api_profile": "no-api-basic", "required_skills": ["sk-a", "sk-b"]},
    )
    _write_skillset(tmp_path, "market-regime", m)
    assert "SK007" in _codes(tmp_path)


def test_sk008_not_disjoint(tmp_path: Path) -> None:
    m = _base_manifest()
    m["recommended_skills"] = ["sk-a"]  # also in required
    _scaffold(tmp_path, m)
    assert "SK008" in _codes(tmp_path)


def test_sk009_unknown_workflow(tmp_path: Path) -> None:
    m = _base_manifest()
    m["related_workflows"] = ["no-such-workflow"]
    _scaffold(tmp_path, m)
    assert "SK009" in _codes(tmp_path)


def test_sk010_coverage_drift(tmp_path: Path) -> None:
    m = _base_manifest()
    # Workflow now requires sk-a, sk-b, sk-e but skillset omits sk-e.
    _write_index(
        tmp_path,
        [_skill(s) for s in ("sk-a", "sk-b", "sk-c", "sk-d", "sk-e")],
    )
    _write_workflow(
        tmp_path,
        "market-regime-daily",
        {"api_profile": "no-api-basic", "required_skills": ["sk-a", "sk-b", "sk-e"]},
    )
    _write_skillset(tmp_path, "market-regime", m)
    assert "SK010" in _codes(tmp_path)


def test_sk011_single_workflow_parity(tmp_path: Path) -> None:
    m = _base_manifest()
    m["required_skills"] = ["sk-a", "sk-b", "sk-c"]  # superset of workflow's
    m["recommended_skills"] = []
    _scaffold(tmp_path, m)
    codes = _codes(tmp_path)
    assert "SK011" in codes  # single workflow → must equal exactly


def test_sk012_api_profile_floor(tmp_path: Path) -> None:
    m = _base_manifest()
    _write_index(tmp_path, [_skill(s) for s in ("sk-a", "sk-b", "sk-c", "sk-d")])
    _write_workflow(
        tmp_path,
        "market-regime-daily",
        {"api_profile": "fmp-required", "required_skills": ["sk-a", "sk-b"]},
    )
    _write_skillset(tmp_path, "market-regime", m)  # manifest still no-api-basic
    assert "SK012" in _codes(tmp_path)


def test_sk012_provider_mismatch_same_rank(tmp_path: Path) -> None:
    # fmp-required workflow under an alpaca-required skillset: same "needs a
    # paid key" tier but different provider → must still fail.
    m = _base_manifest()
    m["api_profile"] = "alpaca-required"
    _write_index(tmp_path, [_skill(s) for s in ("sk-a", "sk-b", "sk-c", "sk-d")])
    _write_workflow(
        tmp_path,
        "market-regime-daily",
        {"api_profile": "fmp-required", "required_skills": ["sk-a", "sk-b"]},
    )
    _write_skillset(tmp_path, "market-regime", m)
    assert "SK012" in _codes(tmp_path)


def test_sk012_mixed_skillset_covers_any_workflow(tmp_path: Path) -> None:
    # `mixed` is the multi-provider umbrella → covers an alpaca-required wf.
    m = _base_manifest()
    m["api_profile"] = "mixed"
    _write_index(tmp_path, [_skill(s) for s in ("sk-a", "sk-b", "sk-c", "sk-d")])
    _write_workflow(
        tmp_path,
        "market-regime-daily",
        {"api_profile": "alpaca-required", "required_skills": ["sk-a", "sk-b"]},
    )
    _write_skillset(tmp_path, "market-regime", m)
    assert "SK012" not in _codes(tmp_path)


@pytest.mark.parametrize("list_field", ["required_skills", "recommended_skills", "optional_skills"])
def test_sk013_paid_required_in_no_api_bundle(tmp_path: Path, list_field: str) -> None:
    m = _base_manifest()
    skills = [
        _skill("sk-a"),
        _skill("sk-b"),
        _skill("sk-c"),
        _skill("sk-d"),
        _skill(
            "sk-paid",
            integrations=[{"id": "fmp", "type": "market_data", "requirement": "required"}],
        ),
    ]
    _write_index(tmp_path, skills)
    _write_workflow(
        tmp_path,
        "market-regime-daily",
        {"api_profile": "no-api-basic", "required_skills": ["sk-a", "sk-b"]},
    )
    if list_field == "required_skills":
        m["required_skills"] = ["sk-a", "sk-b", "sk-paid"]
        # keep SK010/SK011 satisfied: workflow requires only sk-a/sk-b ⊆ req;
        # single-wf parity needs exact match, so align the workflow too.
        _write_workflow(
            tmp_path,
            "market-regime-daily",
            {
                "api_profile": "no-api-basic",
                "required_skills": ["sk-a", "sk-b", "sk-paid"],
            },
        )
    else:
        m[list_field] = ["sk-paid"]
    _write_skillset(tmp_path, "market-regime", m)
    assert "SK013" in _codes(tmp_path)


def test_sk_parse_bad_yaml(tmp_path: Path) -> None:
    (tmp_path / "skillsets").mkdir()
    (tmp_path / "skillsets" / "market-regime.yaml").write_text("id: [unclosed\n", encoding="utf-8")
    assert "SK-PARSE" in _codes(tmp_path)
