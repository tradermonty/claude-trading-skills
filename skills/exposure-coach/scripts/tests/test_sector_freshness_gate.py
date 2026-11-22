"""Sector source date is age-gated against --as-of / --max-age-days (#840)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from provenance_contract import build_provenance
from sector_contract import check_sector_age, parse_sector_input

SCRIPT = Path(__file__).resolve().parents[1] / "calculate_exposure.py"
FIXTURE = Path(__file__).parent / "fixtures" / "sector_rotation_2026-11-21.json"
# 2026-11-21 10:00 America/New_York; the fixture's source date is 2026-11-20.
AS_OF = "2026-11-21T15:00:00Z"


@pytest.fixture
def native_report():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _freshness(report):
    return parse_sector_input(report).details["source_freshness"]


def run_cli(tmp_path, sector, *extra, strict=False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    output_dir = tmp_path / "out"
    args = [sys.executable, str(SCRIPT), "--output-dir", str(output_dir)]
    sector_path = tmp_path / "sector.json"
    sector_path.write_text(json.dumps(sector), encoding="utf-8")
    args += ["--sector", str(sector_path), *extra]
    if strict:
        block = build_provenance(
            provider="fixture",
            endpoint="fixture://primary",
            retrieved_at="2026-11-21T14:00:00Z",
            as_of="2026-11-20",
            run_id="run-a",
        )
        for name in ("breadth", "uptrend"):
            path = tmp_path / f"{name}.json"
            path.write_text(json.dumps({"data_provenance": block}), encoding="utf-8")
            args += [f"--{name}", str(path)]
        args += ["--require-provenance", "--run-id", "run-a"]
    completed = subprocess.run(args, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(next(output_dir.glob("*.json")).read_text(encoding="utf-8"))
    markdown = next(output_dir.glob("*.md")).read_text(encoding="utf-8")
    return completed, payload, markdown


# --- pure check -------------------------------------------------------------


def test_age_within_limit_passes(native_report):
    check = check_sector_age(
        _freshness(native_report), evaluation=AS_OF, max_age_days=3, require_known=True
    )
    assert check.error is None
    assert check.age_days == 1
    assert check.evaluation_date == "2026-11-21"


def test_age_uses_new_york_date_not_utc(native_report):
    # 2026-11-21T03:00Z is still 2026-11-20 in New York, so the age is 0, not 1.
    check = check_sector_age(
        _freshness(native_report),
        evaluation="2026-11-21T03:00:00Z",
        max_age_days=0,
        require_known=False,
    )
    assert check.error is None
    assert check.age_days == 0


def test_stale_source_is_rejected(native_report):
    native_report["meta"]["freshness"]["date"] = "2026-11-14"
    check = check_sector_age(
        _freshness(native_report), evaluation=AS_OF, max_age_days=3, require_known=False
    )
    assert check.error and "stale" in check.error and "7 days" in check.error


def test_age_equal_to_limit_passes(native_report):
    native_report["meta"]["freshness"]["date"] = "2026-11-18"
    check = check_sector_age(
        _freshness(native_report), evaluation=AS_OF, max_age_days=3, require_known=False
    )
    assert check.error is None and check.age_days == 3


def test_source_after_evaluation_is_rejected(native_report):
    native_report["meta"]["freshness"]["date"] = "2026-11-22"
    check = check_sector_age(
        _freshness(native_report), evaluation=AS_OF, max_age_days=3, require_known=False
    )
    assert check.error and "after the evaluation date" in check.error


def test_producer_fresh_claim_does_not_override_age(native_report):
    native_report["meta"]["freshness"] = {"date": "2026-11-01", "is_fresh": True, "warning": None}
    check = check_sector_age(
        _freshness(native_report), evaluation=AS_OF, max_age_days=3, require_known=False
    )
    assert check.error and "stale" in check.error


def test_unknown_freshness_rejected_only_when_required():
    assert check_sector_age(None, evaluation=AS_OF, max_age_days=3, require_known=True).error
    lenient = check_sector_age(None, evaluation=AS_OF, max_age_days=3, require_known=False)
    assert lenient.error is None and lenient.age_days is None


# --- CLI --------------------------------------------------------------------


def test_cli_without_as_of_keeps_producer_claim(tmp_path, native_report):
    native_report["meta"]["freshness"]["date"] = "2026-01-02"
    _, payload, markdown = run_cli(tmp_path, native_report)
    assert payload["component_scores"]["sector_score"] == 3
    assert payload["sector_integration"]["freshness_verified"] is False
    assert "not revalidated" in markdown


def test_cli_as_of_accepts_and_records_check(tmp_path, native_report):
    _, payload, markdown = run_cli(tmp_path, native_report, "--as-of", AS_OF)
    sector = payload["sector_integration"]
    assert payload["component_scores"]["sector_score"] == 3
    assert sector["freshness_verified"] is True
    assert sector["freshness_check"] == {
        "evaluation_date": "2026-11-21",
        "timezone": "America/New_York",
        "max_age_days": 3,
        "age_days": 1,
    }
    assert "age 1 day(s), limit 3" in markdown
    assert "not revalidated" not in markdown


def test_cli_as_of_excludes_stale_sector_everywhere(tmp_path, native_report):
    native_report["meta"]["freshness"]["date"] = "2026-11-14"
    completed, payload, markdown = run_cli(
        tmp_path, native_report, "--as-of", AS_OF, "--max-age-days", "3"
    )
    assert "sector_score" not in payload["component_scores"]
    assert "sector" not in payload["inputs_provided"]
    assert payload["inputs_unparseable"] == ["sector"]
    assert "sector_integration" not in payload
    (warning,) = payload["input_warnings"]["sector"]
    assert "stale" in warning
    assert "stale" in completed.stderr
    assert warning in markdown


def test_cli_strict_mode_accepts_fresh_sector(tmp_path, native_report):
    _, payload, _ = run_cli(tmp_path, native_report, "--as-of", AS_OF, strict=True)
    assert payload["component_scores"]["sector_score"] == 3
    assert payload["sector_integration"]["freshness_verified"] is True


def test_cli_strict_mode_excludes_unknown_freshness(tmp_path, native_report):
    native_report["meta"]["freshness"] = None
    _, payload, _ = run_cli(tmp_path, native_report, "--as-of", AS_OF, strict=True)
    assert "sector_score" not in payload["component_scores"]
    assert payload["inputs_unparseable"] == ["sector"]
    assert "unknown" in payload["input_warnings"]["sector"][0]


def test_cli_non_strict_as_of_keeps_unknown_freshness_with_warning(tmp_path, native_report):
    native_report["meta"]["freshness"] = None
    _, payload, markdown = run_cli(tmp_path, native_report, "--as-of", AS_OF)
    assert payload["component_scores"]["sector_score"] == 3
    sector = payload["sector_integration"]
    assert sector["freshness_verified"] is False
    assert sector["freshness_check"]["age_days"] is None
    assert "could not be applied" in markdown
    assert "pass --as-of" not in markdown


def test_cli_zero_day_limit_boundary(tmp_path, native_report):
    # Source 2026-11-20 is one day before the 2026-11-21 evaluation date.
    _, payload, _ = run_cli(tmp_path, native_report, "--as-of", AS_OF, "--max-age-days", "0")
    assert payload["inputs_unparseable"] == ["sector"]
    _, payload, _ = run_cli(
        tmp_path / "next",
        native_report,
        "--as-of",
        "2026-11-21T03:00:00Z",
        "--max-age-days",
        "0",
    )
    assert payload["component_scores"]["sector_score"] == 3


def test_cli_strict_stale_sector_keeps_market_lineage(tmp_path, native_report):
    native_report["meta"]["freshness"]["date"] = "2026-11-01"
    _, payload, _ = run_cli(tmp_path, native_report, "--as-of", AS_OF, strict=True)
    assert payload["inputs_unparseable"] == ["sector"]
    assert set(payload["input_lineage"]["accepted_inputs"]) == {"breadth", "uptrend"}


def test_cli_strict_mode_excludes_undated_legacy_sector(tmp_path):
    _, payload, _ = run_cli(tmp_path, {"sector_score": 70}, "--as-of", AS_OF, strict=True)
    assert "sector_score" not in payload["component_scores"]
    assert "legacy" in payload["input_warnings"]["sector"][0]


def test_cli_non_strict_as_of_keeps_legacy_sector(tmp_path):
    _, payload, _ = run_cli(tmp_path, {"sector_score": 70}, "--as-of", AS_OF)
    assert payload["component_scores"]["sector_score"] == 70


def _raw_run(tmp_path, *extra):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(tmp_path / "out"), *extra],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "policy,needle",
    [
        (["--as-of", "2026-11-21T10:00:00"], "timezone-aware"),
        (["--as-of", "2026-11-21"], "timezone-aware"),
        (["--as-of", AS_OF, "--max-age-days", "-1"], "nonnegative"),
    ],
)
def test_strict_mode_rejects_invalid_age_policy(tmp_path, native_report, policy, needle):
    sector_path = tmp_path / "sector.json"
    sector_path.write_text(json.dumps(native_report), encoding="utf-8")
    completed = _raw_run(
        tmp_path, "--sector", str(sector_path), "--require-provenance", "--run-id", "r", *policy
    )
    assert completed.returncode == 2
    assert needle in completed.stderr


@pytest.mark.parametrize(
    "policy",
    [
        ["--as-of", "2026-11-21"],
        ["--as-of", "2026-11-21T10:00:00"],
        ["--as-of", AS_OF, "--max-age-days", "-1"],
    ],
)
def test_non_strict_invalid_age_policy_without_sector_still_runs(tmp_path, policy):
    # Non-strict runs ignored --as-of before #840; they must not start failing.
    completed = _raw_run(tmp_path, *policy)
    assert completed.returncode == 0, completed.stderr


def test_non_strict_invalid_as_of_skips_sector_gate_with_warning(tmp_path, native_report):
    native_report["meta"]["freshness"]["date"] = "2026-11-01"
    completed, payload, markdown = run_cli(tmp_path, native_report, "--as-of", "2026-11-21")
    assert payload["component_scores"]["sector_score"] == 3
    assert payload["sector_integration"]["freshness_verified"] is False
    warning = next(w for w in payload["input_warnings"]["sector"] if "age gate skipped" in w)
    assert warning in completed.stderr
    assert warning in markdown
