"""Unit tests for scripts/validate_provenance.py (issue #297 slice 1)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import validate_provenance as vp

VALID = {
    "schema_version": "1.0",
    "provider": "fmp",
    "endpoint": "historical-price-eod",
    "retrieved_at": "2026-08-01T14:30:00Z",
    "as_of": "2026-07-31",
    "timezone": "America/New_York",
    "adjusted": True,
    "point_in_time": True,
    "survivorship_free": False,
    "corporate_actions_handled": True,
}


def test_valid_block_returns_no_errors() -> None:
    assert vp.validate_provenance(VALID) == []


def test_non_mapping_block_rejected() -> None:
    for bad in (None, "fmp", [1, 2], 42):
        assert vp.validate_provenance(bad) == ["data_provenance must be a mapping"]


def test_missing_required_fields_reported() -> None:
    errors = vp.validate_provenance({})
    for field in vp.REQUIRED_FIELDS:
        assert f"missing required field: {field}" in errors
    assert len(errors) == len(vp.REQUIRED_FIELDS)


def test_schema_version_mismatch_reported() -> None:
    block = dict(VALID)
    block["schema_version"] = "0.9"
    errors = vp.validate_provenance(block)
    assert any("does not match contract" in e for e in errors)


def test_string_fields_must_be_nonempty() -> None:
    for field in vp.STRING_FIELDS:
        for bad in (123, "", "   "):
            block = dict(VALID)
            block[field] = bad
            errors = vp.validate_provenance(block)
            assert f"{field} must be a non-empty string" in errors


def test_bool_fields_must_be_boolean() -> None:
    for field in vp.BOOL_FIELDS:
        block = dict(VALID)
        block[field] = "true"
        errors = vp.validate_provenance(block)
        assert any("must be a boolean" in e for e in errors)


def test_retrieved_at_iso_timestamp_required() -> None:
    for bad in ("2026/07/31", "not-a-date", "2026-08-01T14:30:00", 12345, None):
        block = dict(VALID)
        block["retrieved_at"] = bad
        errors = vp.validate_provenance(block)
        assert "retrieved_at must be an ISO-8601 UTC timestamp with timezone" in errors


def test_as_of_iso_date_required() -> None:
    for bad in ("07/31/2026", "2026-13-01", 20260731, None):
        block = dict(VALID)
        block["as_of"] = bad
        errors = vp.validate_provenance(block)
        assert "as_of must be an ISO-8601 date (YYYY-MM-DD)" in errors


def test_as_of_accepts_datetime() -> None:
    block = dict(VALID)
    block["as_of"] = "2026-07-31T14:30:00Z"
    assert vp.validate_provenance(block) == []


def test_timezone_must_be_valid_iana() -> None:
    block = dict(VALID)
    block["timezone"] = "Not/AZone"
    errors = vp.validate_provenance(block)
    assert any("is not a valid IANA timezone" in e for e in errors)


def test_unknown_fields_permitted() -> None:
    block = dict(VALID)
    block["future_field"] = "extended contract"
    assert vp.validate_provenance(block) == []


def test_load_block_json(tmp_path: Path) -> None:
    p = tmp_path / "block.json"
    p.write_text(json.dumps(VALID), encoding="utf-8")
    assert vp.load_block(p) == VALID


def test_load_block_yaml(tmp_path: Path) -> None:
    import yaml

    p = tmp_path / "block.yaml"
    p.write_text(yaml.safe_dump(VALID), encoding="utf-8")
    assert vp.load_block(p) == VALID


def test_load_block_unsupported_suffix_raises(tmp_path: Path) -> None:
    p = tmp_path / "block.txt"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        vp.load_block(p)


def test_main_valid_file(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    p = tmp_path / "block.json"
    p.write_text(json.dumps(VALID), encoding="utf-8")
    assert vp.main(["--file", str(p)]) == 0
    assert "OK data_provenance block valid" in capsys.readouterr().out


def test_main_invalid_file(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    p = tmp_path / "block.json"
    p.write_text(json.dumps({}), encoding="utf-8")
    assert vp.main(["--file", str(p)]) == 1
    assert "INVALID data_provenance block" in capsys.readouterr().out


def test_main_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    missing = tmp_path / "nope.json"
    assert vp.main(["--file", str(missing)]) == 2
    assert "error:" in capsys.readouterr().err


def test_main_malformed_yaml_file(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    p = tmp_path / "block.yaml"
    p.write_text("a: [unclosed\n", encoding="utf-8")
    assert vp.main(["--file", str(p)]) == 2
    assert "error:" in capsys.readouterr().err


def test_main_stdin_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setattr("sys.stdin", type("S", (), {"read": lambda self: json.dumps(VALID)})())
    assert vp.main(["--stdin"]) == 0


def test_main_stdin_yaml(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    import yaml

    monkeypatch.setattr("sys.stdin", type("S", (), {"read": lambda self: yaml.safe_dump(VALID)})())
    assert vp.main(["--stdin"]) == 0


def test_main_stdin_unparseable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr("sys.stdin", type("S", (), {"read": lambda self: "{!not json!"})())
    monkeypatch.setattr("yaml.safe_load", lambda text: (_ for _ in ()).throw(ValueError("bad")))
    assert vp.main(["--stdin"]) == 2
    assert "error:" in capsys.readouterr().err


@pytest.mark.parametrize(
    "source, suffix",
    [
        ("file", ".json"),
        ("file", ".yaml"),
        ("file", ".yml"),
        ("stdin", ".json"),
        ("stdin", ".yaml"),
    ],
)
@pytest.mark.parametrize(
    "payload, exit_code, diagnostic",
    [
        pytest.param(VALID, 0, "OK data_provenance block valid", id="standalone-block"),
        pytest.param(
            {"schema_version": "report-v2", "data_provenance": VALID},
            0,
            "OK data_provenance block valid",
            id="whole-report",
        ),
        pytest.param(
            {**VALID, "data_provenance": {**VALID, "provider": ""}},
            1,
            "provider must be a non-empty string",
            id="invalid-nested-block",
        ),
        pytest.param(
            {**VALID, "data_provenance": None},
            1,
            "data_provenance must be a mapping",
            id="null-nested-block",
        ),
        pytest.param(
            {**VALID, "data_provenance": {}},
            1,
            "missing required field: provider",
            id="empty-nested-block",
        ),
        pytest.param(
            {"skill": "fictional-fixture"},
            1,
            "missing required field: provider",
            id="report-without-block",
        ),
        pytest.param([VALID], 1, "data_provenance must be a mapping", id="non-mapping-document"),
    ],
)
def test_cli_document_input(
    tmp_path: Path,
    source: str,
    suffix: str,
    payload: object,
    exit_code: int,
    diagnostic: str,
) -> None:
    """Validate reports and bare blocks through the actual file/stdin CLI."""
    text = json.dumps(payload) if suffix == ".json" else yaml.safe_dump(payload)
    command = [sys.executable, str(Path(vp.__file__))]
    if source == "file":
        path = tmp_path / f"input{suffix}"
        path.write_text(text, encoding="utf-8")
        command.extend(["--file", str(path)])
    else:
        command.append("--stdin")

    result = subprocess.run(
        command,
        input=text if source == "stdin" else None,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == exit_code, result.stdout + result.stderr
    assert diagnostic in result.stdout
    assert result.stderr == ""


def test_contract_doc_lists_required_fields_and_version() -> None:
    """Drift guard: the documented contract must describe every enforced field."""
    doc = (Path(__file__).resolve().parents[2] / "docs/dev/data-provenance-contract.md").read_text(
        encoding="utf-8"
    )
    assert f"Schema version: **{vp.SCHEMA_VERSION}**" in doc
    for field in vp.REQUIRED_FIELDS + ("schema_version",):
        assert f"`{field}`" in doc, f"contract doc missing required field {field}"
