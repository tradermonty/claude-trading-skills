"""Offline onboarding diagnostics: missing setup must not hide repair hints."""

import importlib.metadata
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import doctor


@pytest.fixture
def root(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/python-support.json").write_text(
        '{"root_project": ">=3.10,<3.14"}', encoding="utf-8"
    )
    return tmp_path


@pytest.mark.parametrize(
    "version,expected",
    [((3, 9), "warning"), ((3, 10), "ok"), ((3, 13), "ok"), ((3, 14), "warning")],
)
def test_python_policy(root, version, expected):
    item = doctor.python_check(root, version)
    assert item["status"] == expected
    if expected == "warning":
        assert "Re-run with Python" in item["hint"]


@pytest.mark.parametrize(
    "content",
    [
        "bad-secret-value",
        "[]",
        '{"root_project": null}',
        '{"root_project": ">=3.14,<3.10"}',
        '{"root_project": ">=3.10; secret"}',
    ],
)
def test_bad_policy_is_unknown_without_content(root, content):
    (root / "config/python-support.json").write_text(content, encoding="utf-8")
    item = doctor.python_check(root, (3, 12))
    assert item["status"] == "unknown"
    assert "secret" not in json.dumps(item)


def test_missing_policy(tmp_path):
    assert doctor.python_check(tmp_path, (3, 12))["status"] == "unknown"


def test_missing_parser_explicitly(monkeypatch, root):
    def unavailable(name):
        raise ImportError("private parser detail")

    monkeypatch.setattr(doctor.importlib, "import_module", unavailable)
    items = doctor.dependency_checks(root)
    assert items[0]["status"] == "unknown"
    assert "private" not in json.dumps(items)
    assert "tomli" in items[0]["hint"]


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"project": None},
        {"project": {"dependencies": "bad"}},
        {"project": {"dependencies": [None]}},
    ],
)
def test_bad_project_shape(monkeypatch, root, data):
    monkeypatch.setattr(doctor, "load_toml", lambda path: data)
    assert doctor.dependency_checks(root)[0]["status"] == "unknown"


def test_parser_error_redacted(monkeypatch, root):
    def broken(path):
        raise ValueError("private-source-secret")

    monkeypatch.setattr(doctor, "load_toml", broken)
    items = doctor.dependency_checks(root)
    assert items[0]["status"] == "unknown"
    assert "private-source-secret" not in json.dumps(items)


def test_distribution_presence_and_unknown_requirements(monkeypatch, root):
    deps = [
        "requests>=2.31.0",
        "absent>=1,<2",
        "bad @ https://secret.example/token",
        "thing[extra]",
        "foo; python_version>'3'",
    ]
    monkeypatch.setattr(doctor, "load_toml", lambda path: {"project": {"dependencies": deps}})

    def installed(name):
        if name == "absent":
            raise importlib.metadata.PackageNotFoundError(name)
        return "0.0"  # Presence must not claim that constraints were satisfied.

    monkeypatch.setattr(doctor.importlib.metadata, "version", installed)
    items = doctor.dependency_checks(root)
    assert [item["status"] for item in items] == ["ok", "warning", "unknown", "unknown", "unknown"]
    assert "not tested" in items[0]["detail"]
    assert "secret.example" not in json.dumps(items)


@pytest.mark.parametrize(
    "env,expected",
    [
        ({}, "warning"),
        ({"ALPACA_API_KEY": "key"}, "warning"),  # pragma: allowlist secret
        (
            {
                "ALPACA_API_KEY": "key",  # pragma: allowlist secret
                "ALPACA_SECRET_KEY": "  ",  # pragma: allowlist secret
            },
            "warning",
        ),
        (
            {
                "ALPACA_API_KEY": "private-key",  # pragma: allowlist secret
                "ALPACA_SECRET_KEY": "private-secret",  # pragma: allowlist secret
            },  # pragma: allowlist secret
            "ok",
        ),  # pragma: allowlist secret
    ],
)
def test_credentials_no_network_no_values(monkeypatch, root, env, expected):
    def no_network(*args, **kwargs):
        pytest.fail("Offline doctor attempted network access")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(doctor, "load_toml", lambda path: {"project": {"dependencies": []}})
    monkeypatch.setattr(doctor.importlib.metadata, "version", lambda name: "1")
    report = doctor.build_report(root, env, (3, 12))
    item = next(item for item in report["checks"] if item["name"] == "credentials:Alpaca")
    assert item["status"] == expected
    assert "private-key" not in json.dumps(report)
    assert "private-secret" not in json.dumps(report)


@pytest.mark.parametrize("json_mode", [False, True])
def test_fresh_cli_outside_repo_without_site_packages(tmp_path, json_mode):
    script = Path(doctor.__file__).resolve()
    env = {
        key: value for key, value in os.environ.items() if key in ("PATH", "SYSTEMROOT", "WINDIR")
    }
    # Even present secrets must not be printed. A local dotenv must not be read.
    env["FMP_API_KEY"] = "unique-private-value"  # pragma: allowlist secret
    (tmp_path / ".env").write_text(
        "FINVIZ_API_KEY=dotenv-private-value\n",  # pragma: allowlist secret
        encoding="utf-8",  # pragma: allowlist secret
    )  # pragma: allowlist secret
    args = [sys.executable, "-S", str(script)] + (["--json"] if json_mode else [])
    result = subprocess.run(args, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    assert result.stderr == ""
    assert "unique-private-value" not in result.stdout
    assert "dotenv-private-value" not in result.stdout
    if json_mode:
        report = json.loads(result.stdout)
        assert report["mode"] == "offline"
        checks = {item["name"]: item for item in report["checks"]}
        assert checks["credentials:FMP"]["status"] == "ok"
        assert checks["credentials:FINVIZ"]["status"] == "warning"
        assert checks["package:pre-commit"]["status"] == "warning"
    else:
        assert "Hint:" in result.stdout
        assert "Skillset readiness" in result.stdout
