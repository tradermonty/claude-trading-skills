"""Issue #783: prerequisites and selection errors cannot propose false passes."""

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def collector():
    path = Path(__file__).resolve().parents[1] / "backfill_security_review.py"
    spec = importlib.util.spec_from_file_location("security_prerequisite_collector", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def skill(tmp_path, body, manifest=True):
    root = tmp_path / "skills" / "probe"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "client.py").write_text(body, encoding="utf-8")
    if manifest:
        (root / "requirements.txt").write_text("# stdlib-only\n", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    "timeout",
    [
        "",
        ", timeout=None",
        ", timeout=True",
        ", timeout=0",
        ", timeout=-2",
        ", timeout=1e999",
        ', timeout=float("nan")',
        ", timeout=(5, None)",
        ", timeout=(5, 1e999)",
        ", timeout=chosen",
        ", **options",
    ],
)
def test_each_network_timeout_must_be_proven(collector, tmp_path, timeout):
    root = skill(tmp_path, f"import requests\nrequests.get(url{timeout})\n")
    checks = collector.mechanical_checks("probe", root)
    assert not checks["clean"]
    assert checks["network_timeout_findings"]


@pytest.mark.parametrize(
    "body",
    [
        "import requests\nrequests.get(url, timeout=5)\nrequests.post(url)\n",
        "# timeout=30\nimport requests\nrequests.get(url)\n",
        "import requests as r\nfetch = r.get\nfetch(url)\n",
        "import requests\ns = requests.Session()\ns = external\ns.get(url, timeout=5)\n",
        "import requests\ndef fetch(transport):\n    return transport.get(url)\n",
        "import requests\ngetattr(requests, method)(url)\n",
        "from urllib.request import urlopen\nurlopen(url)\n",
    ],
)
def test_a_timeout_elsewhere_or_unresolved_dispatch_is_not_proof(collector, tmp_path, body):
    checks = collector.mechanical_checks("probe", skill(tmp_path, body))
    assert not checks["clean"]


@pytest.mark.parametrize(
    "body",
    [
        "import requests as r\nr.get(url, timeout=5)\n",
        "from requests import get as fetch\nfetch(url, timeout=(3, 8))\n",
        "import requests\nclass C:\n    def __init__(self):\n        self.session = requests.Session()\n    def run(self):\n        self.session.get(url, timeout=30)\n",
        "from requests import Session as S\ns = S()\ns.get(url, timeout=4)\n",
        "from urllib.request import urlopen as fetch\nfetch(url, timeout=4)\n",
    ],
)
def test_bounded_recognized_calls_have_per_call_evidence(collector, tmp_path, body):
    checks = collector.mechanical_checks("probe", skill(tmp_path, body))
    assert checks["clean"], checks["findings"]
    assert checks["network_applicability"] == "network"
    assert checks["network_calls"] and all(call["bounded"] for call in checks["network_calls"])


def test_local_url_parsing_needs_no_network_timeout(collector, tmp_path):
    checks = collector.mechanical_checks(
        "probe", skill(tmp_path, 'from urllib.parse import urlencode\nprint(urlencode({"a":1}))\n')
    )
    assert checks["clean"]
    assert checks["network_applicability"] == "not_applicable"
    assert not checks["timeout_present"]


def test_manifest_required_even_for_local_executable_skill(collector, tmp_path):
    checks = collector.mechanical_checks("probe", skill(tmp_path, 'print("local")\n', False))
    assert not checks["clean"]
    assert "requirements.txt" in " ".join(checks["findings"])


def test_prompt_only_skill_needs_no_manifest_or_timeout(collector, tmp_path):
    checks = collector.mechanical_checks("probe", tmp_path)
    assert checks["clean"]
    assert checks["network_applicability"] == "not_applicable"


@pytest.mark.parametrize("body", ["import requests\n", "def broken(:\n"])
def test_unproven_network_or_unparseable_source_is_a_gap(collector, tmp_path, body):
    assert not collector.mechanical_checks("probe", skill(tmp_path, body))["clean"]


def setup_main(collector, monkeypatch, root):
    original = collector.mechanical_checks
    monkeypatch.setattr(collector, "load_index", lambda: {})
    monkeypatch.setattr(collector, "reconcile", lambda _: {"target_skills": ["probe"]})
    monkeypatch.setattr(collector, "mechanical_checks", lambda name: original(name, root))


def test_reviewer_confirmation_cannot_clear_prerequisite_gaps(collector, monkeypatch, tmp_path):
    root = skill(tmp_path, "import requests\nrequests.get(url)\n", False)
    setup_main(collector, monkeypatch, root)
    output = tmp_path / "out"
    assert (
        collector.main(
            ["--skill", "probe", "--reviewer-confirmed", "probe", "--output-dir", str(output)]
        )
        == 0
    )
    row = json.loads((output / "security_review_evidence.json").read_text())["results"][0]
    assert row["proposed_value"] == "gap"
    assert len(row["gap_reasons"]) >= 2


@pytest.mark.parametrize(
    "args",
    [
        ["--skill", "typo"],
        ["--skill", "probe", "--skill", "typo"],
        ["--reviewer-confirmed", "typo"],
        ["--skill", "probe", "--reviewer-confirmed", "typo"],
    ],
)
def test_invalid_ids_fail_before_mutating_report(collector, monkeypatch, tmp_path, capsys, args):
    setup_main(collector, monkeypatch, tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    report = output / "security_review_evidence.json"
    report.write_text("existing report", encoding="utf-8")
    assert collector.main([*args, "--output-dir", str(output)]) != 0
    captured = capsys.readouterr()
    assert "typo" in captured.err and "eligible" in captured.err
    assert not captured.out
    assert report.read_text() == "existing report"


def test_unreadable_source_is_not_local_clean(collector, tmp_path, monkeypatch):
    root = skill(tmp_path, 'print("local")')
    original = Path.read_text

    def unreadable(path, *args, **kwargs):
        if path.name == "client.py":
            raise PermissionError("synthetic denial")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unreadable)
    checks = collector.mechanical_checks("probe", root)
    assert not checks["clean"]
    assert checks["network_applicability"] == "unproven"


def test_invalid_selection_does_not_create_output_directory(collector, tmp_path, monkeypatch):
    setup_main(collector, monkeypatch, tmp_path)
    output = tmp_path / "new-output"
    assert collector.main(["--skill", "unknown", "--output-dir", str(output)]) == 2
    assert not output.exists()


@pytest.mark.parametrize(
    "extra",
    [
        "other = s\nother.get(url)",
        "requests.Session().get(url)",
        "with requests.Session() as other:\n    other.get(url)",
        "fetch = s.get\nfetch(url)",
        'import requests as r\ndef parse():\n    import json as r\n    return r.loads("{}")\nr.get(url)',
        "from requests import *\nget(url)",
    ],
)
def test_mixed_bounded_call_does_not_hide_unproven_dispatch(collector, tmp_path, extra):
    body = "import requests\ns = requests.Session()\ns.get(url, timeout=5)\n" + extra
    checks = collector.mechanical_checks("probe", skill(tmp_path, body))
    assert not checks["clean"]
    assert checks["network_timeout_findings"]


@pytest.mark.parametrize(
    "extra",
    [
        'getattr(s, "get")(url)',
        "s.send(prepared)",
        "def factory():\n    return s\nfactory().get(url)",
        "pool = [s]\npool[0].get(url)",
        "dispatch(s)",
        "other = wrapper(s)\nother.get(url)",
    ],
)
def test_known_client_escapes_are_gaps_even_with_bounded_call(collector, tmp_path, extra):
    body = "import requests\ns = requests.Session()\ns.get(url, timeout=5)\n" + extra
    checks = collector.mechanical_checks("probe", skill(tmp_path, body))
    assert not checks["clean"]
    assert checks["network_timeout_findings"]


@pytest.mark.parametrize(
    "extra",
    [
        "def factory():\n    return requests.get\nfactory()(url)",
        "dispatch(requests.get, url)",
        "from requests import get as fetch\ndef factory():\n    return fetch\nfactory()(url)",
        "from requests import get as fetch\ndispatch(fetch, url)",
    ],
)
def test_network_callable_escapes_are_not_hidden_by_other_bounded_calls(collector, tmp_path, extra):
    body = "import requests\nrequests.get(url, timeout=5)\n" + extra
    checks = collector.mechanical_checks("probe", skill(tmp_path, body))
    assert not checks["clean"]
    assert checks["network_timeout_findings"]
