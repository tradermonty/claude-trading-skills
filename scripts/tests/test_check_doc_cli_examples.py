"""Tests for scripts/check_doc_cli_examples.py (issue #336 gate)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_doc_cli_examples as gate  # noqa: E402


def test_parse_marker_offline_and_ci():
    m = gate._parse_marker("offline")
    assert m.mode == "offline"
    assert m.ci is False
    m = gate._parse_marker("offline ci")
    assert m.mode == "offline"
    assert m.ci is True


def test_parse_marker_api():
    m = gate._parse_marker("api")
    assert m.mode == "api"
    assert m.ci is False


def test_parse_marker_skip():
    m = gate._parse_marker('skip reason="needs api key" owner="@me" expires=2027-01-01')
    assert m.mode == "skip"
    assert m.skip["reason"] == "needs api key"
    assert m.skip["owner"] == "@me"
    assert m.skip["expires"] == "2027-01-01"


def test_extract_invocations_plain_and_uv():
    blk = "python3 a/b.py --x 1\nuv run python3 c/d.py --y 2\n"
    invs = gate.extract_invocations(blk)
    assert len(invs) == 2
    assert invs[0][0] == "python3"
    assert invs[0][1] == "a/b.py"
    assert invs[1][:2] == ["python3", "c/d.py"]


def test_extract_invocations_skips_setup_lines():
    blk = "# comment\nexport KEY=1\npython3 a.py --x\n"
    invs = gate.extract_invocations(blk)
    assert len(invs) == 1
    assert invs[0][1] == "a.py"


def test_extract_invocations_joins_backslash_continuations():
    blk = "python3 a.py --x 1 \\\n  --y 2 \\\n  --z 3\n"
    invs = gate.extract_invocations(blk)
    assert len(invs) == 1
    assert invs[0] == ["python3", "a.py", "--x", "1", "--y", "2", "--z", "3"]


def test_documented_options():
    assert gate.documented_options(["python3", "a.py", "--x", "1", "-v"]) == ["--x", "-v"]
    assert gate.documented_options(["python3", "a.py", "1", "2"]) == []


def test_documented_options_equals_form_and_negative_values():
    assert gate.documented_options(["python3", "a.py", "--foo=bar", "--x", "-1"]) == [
        "--foo",
        "--x",
    ]
    assert gate.documented_options(["python3", "a.py", "--max-position-pct", "10"]) == [
        "--max-position-pct"
    ]


def _write_script(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "tool.py"
    p.write_text(body, encoding="utf-8")
    return p


def test_collect_options_with_parser(tmp_path):
    p = _write_script(
        tmp_path,
        "import argparse\np=argparse.ArgumentParser()\n"
        "p.add_argument('--foo')\np.add_argument('-q', action='store_true')\n"
        "s=p.add_subparsers()\ns.add_parser('run')\n"
        "r=s.add_parser('serve')\nr.add_argument('--port')\n",
    )
    accepted, has = gate.collect_options(p)
    assert has is True
    assert {"--foo", "-q", "run", "serve", "--port"} <= accepted


def test_collect_options_no_parser(tmp_path):
    p = _write_script(tmp_path, "print('hello')\n")
    accepted, has = gate.collect_options(p)
    assert has is False
    assert accepted == set()


def test_validate_flags_no_parser_as_error(tmp_path):
    _write_script(tmp_path, "print('hi')\n")
    md = tmp_path / "doc.md"
    md.write_text(
        "<!-- exec: offline -->\n```bash\npython3 tool.py --ticker AAPL\n```\n", encoding="utf-8"
    )
    findings = []
    gate.validate_target(md, gate.scan_targets([md])[0][1], findings, root=tmp_path)
    assert any("defines no argparse parser" in f.message for f in findings)


def test_validate_flag_not_accepted(tmp_path):
    _write_script(
        tmp_path, "import argparse\np=argparse.ArgumentParser()\np.add_argument('--foo')\n"
    )
    md = tmp_path / "doc.md"
    md.write_text(
        "<!-- exec: offline -->\n```bash\npython3 tool.py --nope 1\n```\n", encoding="utf-8"
    )
    findings = []
    gate.validate_target(md, gate.scan_targets([md])[0][1], findings, root=tmp_path)
    assert any("option not accepted" in f.message for f in findings)


def test_validate_missing_script(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text(
        "<!-- exec: offline -->\n```bash\npython3 does/not/exist.py --x\n```\n", encoding="utf-8"
    )
    findings = []
    gate.validate_target(md, gate.scan_targets([md])[0][1], findings, root=tmp_path)
    assert any("script does not exist" in f.message for f in findings)


def test_skip_missing_fields_is_error(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text(
        "<!-- exec: skip reason=oops owner=@me -->\n```bash\npython3 x.py\n```\n", encoding="utf-8"
    )
    findings = []
    gate.validate_target(md, gate.scan_targets([md])[0][1], findings, root=tmp_path)
    assert any("requires reason" in f.message for f in findings)


def test_skip_passes_with_all_fields(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text(
        "<!-- exec: skip reason=oops owner=@me expires=2099-01-01 -->\n```bash\npython3 x.py\n```\n",
        encoding="utf-8",
    )
    findings = []
    gate.validate_target(md, gate.scan_targets([md])[0][1], findings, root=tmp_path)
    assert findings == []


def test_skip_expired_is_error(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text(
        "<!-- exec: skip reason=oops owner=@me expires=2000-01-01 -->\n```bash\npython3 x.py\n```\n",
        encoding="utf-8",
    )
    findings = []
    gate.validate_target(md, gate.scan_targets([md])[0][1], findings, root=tmp_path)
    assert any("expired" in f.message for f in findings)


def test_parity_detects_drift(tmp_path):
    en = tmp_path / "en.md"
    ja = tmp_path / "ja.md"
    en.write_text("`python3 tools/a.py`\n", encoding="utf-8")
    ja.write_text("`python3 tools/b.py`\n", encoding="utf-8")
    findings = []
    gate.validate_en_ja_pairs(["en.md:ja.md"], findings, root=tmp_path)
    assert any("missing in JA" in f.message or "missing in EN" in f.message for f in findings)


def test_execute_offline_ci_isolated(tmp_path):
    script = _write_script(
        tmp_path,
        "import pathlib, os\n"
        "os.makedirs('reports', exist_ok=True)\n"
        "pathlib.Path('reports/out.txt').write_text('ok', encoding='utf-8')\n"
        "print('done')\n",
    )
    md = tmp_path / "doc.md"
    md.write_text(
        f"<!-- exec: offline ci -->\n```bash\npython3 {script.name}\n```\n", encoding="utf-8"
    )
    ran, errors = gate.run_execute(["doc.md"], ci_only=True, root=tmp_path)
    assert errors == []
    assert len(ran) == 1
    # repo root not mutated: cwd-relative reports/ went to the temp dir
    assert not (tmp_path / "reports").exists()


def test_execute_ci_only_skips_plain_offline(tmp_path):
    script = _write_script(tmp_path, "print('done')\n")
    md = tmp_path / "doc.md"
    md.write_text(
        f"<!-- exec: offline -->\n```bash\npython3 {script.name}\n```\n", encoding="utf-8"
    )
    ran, errors = gate.run_execute(["doc.md"], ci_only=True, root=tmp_path)
    assert errors == []
    assert ran == []


def test_api_ci_rejected(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("<!-- exec: api ci -->\n```bash\npython3 tool.py\n```\n", encoding="utf-8")
    findings = []
    gate.validate_target(md, gate.scan_targets([md])[0][1], findings, root=tmp_path)
    assert any("cannot be ci" in f.message for f in findings)


def test_unknown_mode_is_error(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("<!-- exec: offlinee -->\n```bash\npython3 tool.py\n```\n", encoding="utf-8")
    findings = []
    gate.validate_target(md, gate.scan_targets([md])[0][1], findings, root=tmp_path)
    assert any("unknown exec marker mode" in f.message for f in findings)


def test_equals_form_option_against_script(tmp_path):
    script = tmp_path / "tool.py"
    script.write_text(
        "import argparse\np = argparse.ArgumentParser()\np.add_argument('--foo')\n",
        encoding="utf-8",
    )
    md = tmp_path / "doc.md"
    md.write_text(
        "<!-- exec: offline -->\n```bash\npython3 tool.py --foo=bar\n```\n", encoding="utf-8"
    )
    findings = []
    gate.validate_target(md, gate.scan_targets([md])[0][1], findings, root=tmp_path)
    assert findings == []


# ---------------------------------------------------------------------------
# Review-round raised: repo-mutation guard + stdlib-only ci execution + targets
# ---------------------------------------------------------------------------


def _init_git_repo(tmp_path: Path) -> Path:
    import subprocess as sp

    # Pre-push hooks export GIT_INDEX_FILE/GIT_DIR; scrub them so the
    # fixture repo initializes on its own machinery (mirrors the guard).
    git_env = dict(os.environ)
    for key in [k for k in git_env if k.startswith("GIT_")]:
        git_env.pop(key)

    root = tmp_path / "gitsrc"
    root.mkdir()
    sp.run(["git", "init", "-q", str(root)], check=True, capture_output=True, env=git_env)
    sp.run(
        ["git", "-C", str(root), "config", "user.email", "t@example.com"], check=True, env=git_env
    )
    sp.run(["git", "-C", str(root), "config", "user.name", "t"], check=True, env=git_env)
    (root / "doc.md").write_text(
        "<!-- exec: offline ci -->\n```bash\npython3 tool.py\n```\n", encoding="utf-8"
    )
    (root / "tool.py").write_text("print('done')\n", encoding="utf-8")
    sp.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True, env=git_env)
    sp.run(
        ["git", "-C", str(root), "commit", "-qm", "init"],
        check=True,
        capture_output=True,
        env=git_env,
    )
    return root


def test_execute_mutating_block_is_guarded(tmp_path):
    root = _init_git_repo(tmp_path)
    script = root / "tool.py"
    script.write_text(
        "import pathlib\n"
        # scripts that anchor outputs to their own location (repo-relative via
        # __file__) escape the temp cwd — this is the class the git-status
        # guard exists for
        "repo = pathlib.Path(__file__).resolve().parent\n"
        "pathlib.Path(repo / 'leaked.txt').write_text('mutated', encoding='utf-8')\n"
        "print('done')\n",
        encoding="utf-8",
    )
    (root / "doc.md").write_text(
        "<!-- exec: offline ci -->\n```bash\npython3 tool.py\n```\n", encoding="utf-8"
    )
    ran, errors = gate.run_execute(["doc.md"], ci_only=True, root=root)
    assert ran == []
    assert any("mutated the repository" in e for e in errors)
    assert (root / "leaked.txt").exists()  # the write happened and was caught


def test_execute_clean_block_passes_guard(tmp_path):
    root = _init_git_repo(tmp_path)
    (root / "tool.py").write_text(
        "import pathlib, os\n"
        "os.makedirs('reports', exist_ok=True)\n"
        "pathlib.Path('reports/out.txt').write_text('ok', encoding='utf-8')\n"
        "print('done')\n",
        encoding="utf-8",
    )
    ran, errors = gate.run_execute(["doc.md"], ci_only=True, root=root)
    assert errors == []
    assert len(ran) == 1
    assert not (root / "reports").exists()


def test_git_status_snapshot_disabled_outside_repo(tmp_path):
    assert gate._git_status_snapshot(tmp_path) is None


def test_ci_execute_runs_stdlib_only():
    captured = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    root = tmp_path_on_demand()
    (root / "tool.py").write_text("print('hi')\n", encoding="utf-8")
    (root / "doc.md").write_text(
        "<!-- exec: offline ci -->\n```bash\npython3 tool.py\n```\n", encoding="utf-8"
    )
    orig_run = gate.subprocess.run
    orig_snapshot = gate._git_status_snapshot
    gate.subprocess.run = fake_run
    gate._git_status_snapshot = lambda _root: None
    try:
        ran, errors = gate.run_execute(["doc.md"], ci_only=True, root=root)
    finally:
        gate.subprocess.run = orig_run
        gate._git_status_snapshot = orig_snapshot
    assert errors == []
    assert captured and captured[0][:2] == ["python3", "-S"]


def tmp_path_on_demand():
    root = Path(tempfile.mkdtemp())
    return root


def test_plain_execute_does_not_use_S_flag(tmp_path):
    captured = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    orig_run = gate.subprocess.run
    orig_snapshot = gate._git_status_snapshot
    gate.subprocess.run = fake_run
    gate._git_status_snapshot = lambda root: None
    try:
        (tmp_path / "tool.py").write_text("print('hi')\n", encoding="utf-8")
        (tmp_path / "doc.md").write_text(
            f"<!-- exec: offline -->\n```bash\npython3 {tmp_path / 'tool.py'}\n```\n",
            encoding="utf-8",
        )
        ran, errors = gate.run_execute(["doc.md"], ci_only=False, root=tmp_path)
    finally:
        gate.subprocess.run = orig_run
        gate._git_status_snapshot = orig_snapshot
    assert errors == []
    assert (
        captured and captured[0][:2] == ["python3", "--0"] if False else captured[0][0] == "python3"
    )
    assert "-S" not in captured[0]


def test_glob_targets_expand_skills(tmp_path):
    skill_md = tmp_path / "skills" / "demo" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text(
        "<!-- exec: offline -->\n```bash\npython3 nope_missing.py\n```\n", encoding="utf-8"
    )
    findings = gate.run_validate(["skills/*/SKILL.md", "README.md"], [], root=tmp_path)
    # missing README.md is reported, and the SKILL.md fence references a
    # nonexistent script — the widened targets catch it
    assert any("target file missing" in f.message for f in findings)
    assert any("script does not exist" in f.message for f in findings)
