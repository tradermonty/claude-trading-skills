"""Adversarial offline checks for the supply-chain policy."""

import datetime as dt
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "supply_chain", Path(__file__).resolve().parents[1] / "check_supply_chain.py"
)
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


def exception(**overrides):
    return dict(
        package="demo",
        version="1.0",
        advisory="GHSA-demo",
        owner="security",
        reason="Tracked upgrade",
        expires_on="2099-01-01",
        **overrides,
    )


def exceptions_file(tmp_path, entries):
    path = tmp_path / "exceptions.json"
    path.write_text(json.dumps({"schema_version": 1, "vulnerabilities": entries}))
    return path


def test_exceptions_valid_and_normalized(tmp_path):
    item = exception()
    item["package"] = "Some_Package"
    assert policy.load_exceptions(exceptions_file(tmp_path, [item])) == {
        ("some-package", "1.0", "GHSA-demo")
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("expires_on", "2020-01-01"),
        ("expires_on", "2099-02-30"),
        ("expires_on", "20990101"),
        ("expires_on", "2099-01-01T00:00:00Z"),
        ("owner", ""),
        ("reason", " "),
        ("advisory", None),
        ("package", "*"),
        ("version", "*"),
        ("version", ">=1"),
    ],
)
def test_exception_invalid_fields(tmp_path, field, value):
    item = exception()
    item[field] = value
    with pytest.raises(policy.PolicyError):
        policy.load_exceptions(exceptions_file(tmp_path, [item]))


def test_expiry_today_utc(tmp_path):
    with pytest.raises(policy.PolicyError, match="today"):
        policy.load_exceptions(exceptions_file(tmp_path, [exception()]), dt.date(2099, 1, 1))


@pytest.mark.parametrize(
    "data",
    [
        {"schema_version": True, "vulnerabilities": []},
        {"schema_version": 1, "vulnerabilities": [], "licenses": []},
        {"schema_version": 1, "vulnerabilities": {}},
        {"schema_version": 1, "vulnerabilities": [dict(exception(), license="MIT")]},
        {"schema_version": 1, "vulnerabilities": [exception(), exception()]},
    ],
)
def test_schema_rejects_unknown_and_duplicates(tmp_path, data):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(policy.PolicyError):
        policy.load_exceptions(path)


def test_duplicate_json_keys():
    with pytest.raises(policy.PolicyError):
        policy.read_json('{"schema_version": 1, "schema_version": 1}')


def workflow(tmp_path, uses):
    directory = tmp_path / ".github/workflows"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ci.yml").write_text(f"jobs:\n  check:\n    uses: {uses}\n")


@pytest.mark.parametrize(
    "ref",
    [
        "actions/checkout@v4",
        "actions/checkout@main",
        "org/repo/.github/workflows/ci.yml@v1",
        "docker://alpine:3",
        "${{ matrix.action }}",
        "./missing",
    ],
)
def test_mutable_or_missing_actions_rejected(tmp_path, ref):
    workflow(tmp_path, ref)
    with pytest.raises(policy.PolicyError):
        policy.check_actions(tmp_path)


@pytest.mark.parametrize(
    "ref",
    [
        "actions/checkout@" + "a" * 40,
        "org/repo/.github/workflows/ci.yml@" + "B" * 40,
        "docker://alpine@sha256:" + "a" * 64,
    ],
)
def test_immutable_actions_accepted(tmp_path, ref):
    workflow(tmp_path, ref)
    assert policy.check_actions(tmp_path) == 1


def test_nested_local_action_inspected(tmp_path):
    workflow(tmp_path, "./.github/actions/test")
    directory = tmp_path / ".github/actions/test"
    directory.mkdir(parents=True)
    action = directory / "action.yml"
    action.write_text("runs:\n  using: composite\n  steps:\n    - uses: actions/checkout@v4\n")
    with pytest.raises(policy.PolicyError, match="full commit SHA"):
        policy.check_actions(tmp_path)
    action.write_text("runs:\n  using: composite\n  steps:\n    - run: echo test\n")
    assert policy.check_actions(tmp_path) == 2


def lock_file(tmp_path, source='registry = "https://pypi.org/simple"'):
    path = tmp_path / "uv.lock"
    path.write_text(f"""version = 1
[[package]]
name = "claude-trading-skills"
version = "0.1.0"
source = {{ virtual = "." }}
[[package]]
name = "Demo"
version = "1.0"
source = {{ {source} }}
resolution-markers = ["python_version < '3.10'"]
[[package]]
name = "demo"
version = "2.0"
source = {{ registry = "https://pypi.org/simple" }}
resolution-markers = ["sys_platform == 'win32'"]
""")
    return path


def test_lock_all_markers_and_multiple_versions(tmp_path):
    inventory = policy.lock_inventory(lock_file(tmp_path))
    assert inventory == {("demo", "1.0"), ("demo", "2.0")}
    assert policy.audit_batches(inventory) == [[("demo", "1.0")], [("demo", "2.0")]]


@pytest.mark.parametrize(
    "source",
    [
        'git = "https://example.com/repo"',
        'editable = "."',
        'registry = "https://other.example/simple"',
        'virtual = "."',
    ],
)
def test_unsupported_lock_source(tmp_path, source):
    with pytest.raises(policy.PolicyError):
        policy.lock_inventory(lock_file(tmp_path, source))


def report(vulns=None):
    return {"dependencies": [{"name": "demo", "version": "1.0", "vulns": vulns or []}]}


def test_severity_irrelevant_and_exact_alias_exception():
    data = report([{"id": "CVE-123", "aliases": ["GHSA-demo"], "severity": "unknown"}])
    expected = {("demo", "1.0")}
    assert len(policy.evaluate_report(data, expected, set())) == 1
    assert policy.evaluate_report(data, expected, {("demo", "1.0", "GHSA-demo")}) == []
    assert policy.evaluate_report(data, expected, {("demo", "2.0", "GHSA-demo")})
    assert policy.evaluate_report(data, expected, {("other", "1.0", "GHSA-demo")})


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"dependencies": []},
        {"dependencies": [{"name": "demo", "skip_reason": "unsupported"}]},
        {"dependencies": [{"name": "demo", "version": "1.0"}]},
        {"dependencies": report()["dependencies"] * 2},
        report([{}]),
        report([{"id": "CVE", "aliases": "GHSA"}]),
        report([{"id": ""}]),
    ],
)
def test_incomplete_malformed_reports_fail_closed(data):
    with pytest.raises(policy.PolicyError):
        policy.evaluate_report(data, {("demo", "1.0")}, set())


def test_clean_complete_report():
    assert policy.evaluate_report(report(), {("demo", "1.0")}, set()) == []


def test_audit_batches_mocked_cli(tmp_path, monkeypatch):
    calls = []

    def run(command, **kwargs):
        pins = Path(command[command.index("-r") + 1]).read_text()
        calls.append(pins)
        assert command[:3] == [policy.sys.executable, "-m", "pip_audit"]
        assert "--no-deps" in command and "--disable-pip" in command
        version = pins.strip().split("==")[1]
        data = report()
        data["dependencies"][0]["version"] = version
        return subprocess.CompletedProcess(command, 0, json.dumps(data), "")

    monkeypatch.setattr(policy.subprocess, "run", run)
    output = tmp_path / "report.json"
    assert policy.audit_lock(lock_file(tmp_path), set(), output) == 0
    assert calls == ["demo==1.0\n", "demo==2.0\n"]
    data = json.loads(output.read_text())
    assert len(data["inventory"]) == len(data["dependencies"]) == 2


@pytest.mark.parametrize(
    "code,stdout",
    [
        (2, "{}"),
        (1, json.dumps(report())),
        (0, "not json"),
        (0, '{"dependencies": []}'),
        (0, json.dumps(report([{"id": "CVE"}]))),
        (1, json.dumps(report([{"id": "CVE"}]))),
    ],
)
def test_audit_failure_writes_report(tmp_path, monkeypatch, code, stdout):
    monkeypatch.setattr(
        policy.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, code, stdout, "error"),
    )
    output = tmp_path / "report.json"
    assert policy.audit_lock(lock_file(tmp_path), set(), output) == 1
    data = json.loads(output.read_text())
    assert data["errors"] or data.get("blocked")


def test_audit_timeout_writes_report(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("pip-audit", 600)

    monkeypatch.setattr(policy.subprocess, "run", fail)
    output = tmp_path / "report.json"
    assert policy.audit_lock(lock_file(tmp_path), set(), output) == 1
    assert json.loads(output.read_text())["errors"]


def test_exact_project_root_editable_exempt(tmp_path):
    path = lock_file(tmp_path)
    path.write_text(path.read_text().replace('virtual = "."', 'editable = "."'))
    assert policy.lock_inventory(path) == {("demo", "1.0"), ("demo", "2.0")}


def test_advisory_wildcard_rejected(tmp_path):
    item = exception()
    item["advisory"] = "*"
    with pytest.raises(policy.PolicyError):
        policy.load_exceptions(exceptions_file(tmp_path, [item]))


@pytest.mark.parametrize("image", ["docker://alpine:latest", "Dockerfile", "./Dockerfile", None])
def test_local_docker_action_rejects_unpinned_image(tmp_path, image):
    workflow(tmp_path, "./.github/actions/test")
    directory = tmp_path / ".github/actions/test"
    directory.mkdir(parents=True)
    (directory / "action.yml").write_text(
        policy.yaml.safe_dump({"runs": {"using": "docker", "image": image}})
    )
    with pytest.raises(policy.PolicyError, match="remote sha256 digest"):
        policy.check_actions(tmp_path)


def test_local_docker_action_accepts_digest(tmp_path):
    workflow(tmp_path, "./.github/actions/test")
    directory = tmp_path / ".github/actions/test"
    directory.mkdir(parents=True)
    (directory / "action.yaml").write_text(
        policy.yaml.safe_dump(
            {"runs": {"using": "docker", "image": "docker://alpine@sha256:" + "a" * 64}}
        )
    )
    assert policy.check_actions(tmp_path) == 2


def test_duplicate_yaml_uses_rejected(tmp_path):
    workflow(tmp_path, "actions/checkout@" + "a" * 40)
    path = tmp_path / ".github/workflows/ci.yml"
    path.write_text(
        "jobs:\n  check:\n    uses: actions/checkout@main\n    uses: actions/checkout@"
        + "a" * 40
        + "\n"
    )
    with pytest.raises(policy.PolicyError, match="Duplicate YAML key"):
        policy.check_actions(tmp_path)
