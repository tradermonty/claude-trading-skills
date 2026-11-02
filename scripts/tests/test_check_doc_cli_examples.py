"""Tests for scripts/check_doc_cli_examples.py (issue #336 gate)."""

from __future__ import annotations

import os
import re
import shlex
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_doc_cli_examples as gate  # noqa: E402


def _root_documents(root: Path) -> None:
    for name in ("CLAUDE.md", "README.md", "README.ja.md"):
        (root / name).write_text("# Root guide\n", encoding="utf-8")


@pytest.mark.parametrize("language", ["en", "ja"])
@pytest.mark.parametrize(
    "relative", ["getting-started.md", "skills/demo.md", "playbooks/deep/demo.md"]
)
def test_default_targets_check_recursive_site_script_paths(tmp_path, language, relative):
    _root_documents(tmp_path)
    page = tmp_path / "docs" / language / relative
    page.parent.mkdir(parents=True)
    page.write_text("# Guide\n\n```bash\npython3 skills/demo/scripts/missing.py\n```\n")
    findings = gate.run_validate(gate.DEFAULT_TARGETS, [], root=tmp_path)
    assert len(findings) == 1
    assert findings[0].file == str(page)
    assert findings[0].line_no == 4
    assert "script does not exist: skills/demo/scripts/missing.py" in findings[0].message


@pytest.mark.parametrize("fence", ["bash", "sh", "shell", "console"])
def test_site_path_validation_is_static_and_accepts_root_commands(tmp_path, monkeypatch, fence):
    _root_documents(tmp_path)
    script = tmp_path / "skills/demo/scripts/tool.py"
    script.parent.mkdir(parents=True)
    script.write_text("raise RuntimeError('must never execute')\n")
    page = tmp_path / "docs/en/skills/demo.md"
    page.parent.mkdir(parents=True)
    prefix = "$ " if fence == "console" else ""
    page.write_text(f"```{fence}\n{prefix}python3 skills/demo/scripts/tool.py\n```\n")

    def unexpected_execution(*args, **kwargs):
        raise AssertionError("validate must never execute a subprocess")

    monkeypatch.setattr(gate.subprocess, "run", unexpected_execution)
    assert gate.run_validate(gate.DEFAULT_TARGETS, [], root=tmp_path) == []
    script.unlink()
    assert any(
        "script does not exist" in f.message
        for f in gate.run_validate(gate.DEFAULT_TARGETS, [], root=tmp_path)
    )


def test_site_marker_rules_still_reject_expired_skips_and_bad_options(tmp_path):
    _root_documents(tmp_path)
    script = tmp_path / "skills/demo/scripts/tool.py"
    script.parent.mkdir(parents=True)
    script.write_text("import argparse\np = argparse.ArgumentParser()\np.add_argument('--valid')\n")
    page = tmp_path / "docs/ja/skills/demo.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        '<!-- exec: skip reason="temporary" owner="maintainer" expires=2000-01-01 -->\n'
        "```bash\npython3 missing.py\n```\n\n"
        "<!-- exec: api -->\n```bash\npython3 skills/demo/scripts/tool.py --invalid\n```\n"
    )
    findings = gate.run_validate(gate.DEFAULT_TARGETS, [], root=tmp_path)
    assert any("skip is expired" in f.message for f in findings)
    assert any("option not accepted" in f.message for f in findings)


def test_site_docs_trigger_pre_commit_cli_validation():
    config = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / ".pre-commit-config.yaml").read_text()
    )
    hook = next(
        hook
        for repo in config["repos"]
        for hook in repo["hooks"]
        if hook["id"] == "docs-cli-examples"
    )
    for page in (
        "docs/en/getting-started.md",
        "docs/ja/skills/demo.md",
        "docs/en/playbooks/deep/demo.md",
    ):
        assert re.search(hook["files"], page), page
    assert hook["entry"] == "python3 scripts/check_doc_cli_examples.py validate"
    assert hook["pass_filenames"] is False


def test_public_execute_cli_keeps_prior_default_scope(monkeypatch):
    captured = []

    def capture(targets, ci_only):
        captured.append((list(targets), ci_only))
        return [], []

    monkeypatch.setattr(gate, "run_execute", capture)
    assert gate.main(["execute", "--ci"]) == 0
    assert captured == [(["CLAUDE.md", "README.md", "README.ja.md", "skills/*/SKILL.md"], True)]
    captured.clear()
    assert gate.main(["execute", "--ci", "--targets", "docs/en/guide.md"]) == 0
    assert captured == [(["docs/en/guide.md"], True)]


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
    assert captured and captured[0][:2] == [sys.executable, "-S"]


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
            f"<!-- exec: offline -->\n```bash\npython3 {shlex.quote((tmp_path / 'tool.py').as_posix())}\n```\n",
            encoding="utf-8",
        )
        ran, errors = gate.run_execute(["doc.md"], ci_only=False, root=tmp_path)
    finally:
        gate.subprocess.run = orig_run
        gate._git_status_snapshot = orig_snapshot
    assert errors == []
    assert captured and captured[0][0] == sys.executable
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


def test_unmarked_root_script_paths_checked_in_claude_and_readmes(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "exists.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(
        "Heading\n```bash\npython3 scripts/exists.py\n"
        "python3 absent-skill/scripts/missing.py\n```\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "```bash\npython scripts/missing-readme.py\n```\n", encoding="utf-8"
    )
    (tmp_path / "README.ja.md").write_text("```bash\npython3 scripts/exists.py\n```\n")
    findings = gate.run_validate(gate.DEFAULT_TARGETS, [], root=tmp_path)
    assert [(f.file, f.line_no, f.message) for f in findings] == [
        (
            str(tmp_path / "CLAUDE.md"),
            4,
            "script does not exist: absent-skill/scripts/missing.py",
        ),
        (str(tmp_path / "README.md"), 2, "script does not exist: scripts/missing-readme.py"),
    ]


def test_unmarked_gate_ignores_modules_and_external_paths(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```bash\npython3 -m pytest scripts/tests\n"
        "python3 /opt/vendor/scripts/tool.py\n"
        "python3 ~/plugins/scripts/tool.py\n"
        "python3 ../other/scripts/tool.py\n```\n",
        encoding="utf-8",
    )
    assert gate.run_validate(["CLAUDE.md"], [], root=tmp_path) == []


def test_unmarked_gate_handles_python_options_and_shell_wrappers(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```bash\n"
        "echo python3 scripts/display-only.py\n"
        "python3 -m pytest scripts/tests\n"
        "python3 -u scripts/missing-u.py && python3 -B scripts/missing-b.py\n"
        "env MODE=test python3 -I scripts/missing-env.py\n"
        "env -u FMP_API_KEY python3 scripts/missing-env-unset.py\n"
        "uv run --locked python3 -X dev scripts/missing-uv.py\n"
        "```\n",
        encoding="utf-8",
    )
    findings = gate.run_validate(["CLAUDE.md"], [], root=tmp_path)
    assert [(f.line_no, f.message) for f in findings] == [
        (4, "script does not exist: scripts/missing-u.py"),
        (4, "script does not exist: scripts/missing-b.py"),
        (5, "script does not exist: scripts/missing-env.py"),
        (6, "script does not exist: scripts/missing-env-unset.py"),
        (7, "script does not exist: scripts/missing-uv.py"),
    ]


def test_unmarked_gate_checks_script_directly_after_uv_run(tmp_path):
    scripts = tmp_path / "skills" / "demo" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "ok.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(
        "```bash\n"
        "uv run skills/nope/scripts/x.py --flag\n"
        "uv run skills/demo/scripts/ok.py --project-root .\n"
        "uv run --with pkg skills/demo/scripts/ok.py\n"
        "uv run --project . --with=pkg skills/demo/scripts/ok.py\n"
        "uv run --with pkg skills/nope/scripts/y.py\n"
        "uv run --project . skills/nope/scripts/z.py\n"
        "uv run python3 scripts/missing-py.py\n"
        "uv run pytest skills/demo/scripts/tests\n"
        "uv run ruff check scripts/\n"
        "```\n",
        encoding="utf-8",
    )
    findings = gate.run_validate(["CLAUDE.md"], [], root=tmp_path)
    assert [(f.line_no, f.message) for f in findings] == [
        (2, "script does not exist: skills/nope/scripts/x.py"),
        (6, "script does not exist: skills/nope/scripts/y.py"),
        (7, "script does not exist: skills/nope/scripts/z.py"),
        (8, "script does not exist: scripts/missing-py.py"),
    ]


def test_unmarked_gate_resolves_in_root_parent_segments(tmp_path):
    scripts = tmp_path / "skills" / "demo" / "scripts"
    scripts.mkdir(parents=True)
    (scripts.parent / "tool.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(
        "```bash\n"
        "python3 skills/demo/scripts/../tool.py\n"
        "python3 skills/demo/scripts/../../../../outside.py\n"
        "```\n",
        encoding="utf-8",
    )
    findings = gate.run_validate(["CLAUDE.md"], [], root=tmp_path)
    assert [(f.line_no, f.message) for f in findings] == [
        (3, "script escapes root: skills/demo/scripts/../../../../outside.py")
    ]


def test_unmarked_gate_keeps_skip_and_marked_execution_scope(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        '<!-- exec: skip reason="external" owner="@me" expires=2099-01-01 -->\n'
        "```bash\npython3 scripts/intentionally-missing.py\n```\n"
        "```bash\npython3 scripts/also-missing.py\n```\n",
        encoding="utf-8",
    )
    findings = gate.run_validate(["CLAUDE.md"], [], root=tmp_path)
    assert len(findings) == 1
    assert findings[0].line_no == 6
    assert "also-missing.py" in findings[0].message
    ran, errors = gate.run_execute(["CLAUDE.md"], ci_only=False, root=tmp_path)
    assert ran == errors == []


def test_unmarked_gate_reports_each_command_start_line(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```bash\n"
        "python3 skills/one/scripts/a.py " + "\\\n"
        "  --arg value\n"
        "python3 skills/two/scripts/b.py\n"
        "```\n",
        encoding="utf-8",
    )
    findings = gate.run_validate(["CLAUDE.md"], [], root=tmp_path)
    assert [(f.line_no, f.message) for f in findings] == [
        (2, "script does not exist: skills/one/scripts/a.py"),
        (4, "script does not exist: skills/two/scripts/b.py"),
    ]


def test_unmarked_gate_validates_trailing_continuation_command(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```bash\npython3 skills/x/scripts/missing.py \\\n```\n",
        encoding="utf-8",
    )
    findings = gate.run_validate(["CLAUDE.md"], [], root=tmp_path)
    assert [(f.line_no, f.message) for f in findings] == [
        (2, "script does not exist: skills/x/scripts/missing.py"),
    ]


def test_run_validate_absolute_target_outside_root_does_not_crash(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("```bash\npython3 skills/x/scripts/missing.py\n```\n", encoding="utf-8")
    findings = gate.run_validate([str(outside)], [], root=root)
    # Outside the repo root: not a root doc, so the unmarked path check is skipped.
    assert findings == []


def test_current_default_documented_examples_validate():
    assert gate.run_validate(gate.DEFAULT_TARGETS, gate.DEFAULT_EN_JA_PAIRS) == []


def test_shell_shapes_and_output(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/ok.py").write_text("pass\n")
    for fence in ("bash", "sh", "shell", "console"):
        for wrapper in ("", "$ ", "sudo ", "time ", "nohup ", "sudo time nohup "):
            prompt = "$ " if fence == "console" and not wrapper.startswith("$") else ""
            (tmp_path / "CLAUDE.md").write_text(
                f"```{fence}\n{prompt}{wrapper}python3 scripts/ok.py\n"
                f"{prompt}{wrapper}uv run --with pkg scripts/missing.py\n```\n"
            )
            findings = gate.run_validate(["CLAUDE.md"], [], root=tmp_path)
            assert len(findings) == 1, (fence, wrapper, findings)
    (tmp_path / "CLAUDE.md").write_text(
        "```console\npython3 scripts/output.py\n$ python3 scripts/ok.py\n```\n"
        "```notbash\npython3 scripts/display.py\n```\n"
    )
    assert gate.run_validate(["CLAUDE.md"], [], root=tmp_path) == []


def test_cd_and_directory_context(tmp_path):
    for cd in ("cd subdir", "sudo cd subdir", "time cd subdir"):
        (tmp_path / "CLAUDE.md").write_text(
            f"```sh\n{cd} && python3 scripts/wrong-root.py\npython3 scripts/later.py\n```\n"
        )
        assert gate.run_validate(["CLAUDE.md"], [], root=tmp_path) == []
    (tmp_path / "CLAUDE.md").write_text(
        "```sh\nuv run --directory subdir scripts/missing.py\n"
        "uv run --directory=subdir scripts/missing.py\n"
        "uv run --project subdir scripts/checked.py\n```\n"
    )
    findings = gate.run_validate(["CLAUDE.md"], [], root=tmp_path)
    assert [f.message for f in findings] == ["script does not exist: scripts/checked.py"]


def test_heredoc_bodies_and_resume(tmp_path):
    for delimiter in ("EOF", "'EOF'", '"EOF"', "-EOF"):
        body_prefix = "\t" if delimiter.startswith("-") else ""
        (tmp_path / "CLAUDE.md").write_text(
            f"```shell\ncat <<{delimiter}\n{body_prefix}python3 scripts/body.py\n"
            f"{body_prefix}EOF\npython3 scripts/after.py\n```\n"
        )
        findings = gate.run_validate(["CLAUDE.md"], [], root=tmp_path)
        assert [f.message for f in findings] == ["script does not exist: scripts/after.py"]


def test_console_continuation_and_literal_heredoc(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```console\n$ uv run --with pkg \\\n  scripts/missing.py\n"
        '$ echo "<<" EOF\n$ python3 scripts/after.py\n```\n'
    )
    findings = gate.run_validate(["CLAUDE.md"], [], root=tmp_path)
    assert len(findings) == 2


def test_quoted_heredoc_dash_and_tab_modifier(tmp_path):
    for opener, end in (
        ("<<-'EOF'", "\tEOF"),
        ("<<- 'EOF'", "\tEOF"),
        ("<<'-EOF'", "-EOF"),
        ("<< -EOF", "-EOF"),
    ):
        (tmp_path / "CLAUDE.md").write_text(
            f"```sh\ncat {opener}\npython3 scripts/body.py\n{end}\npython3 scripts/after.py\n```\n"
        )
        findings = gate.run_validate(["CLAUDE.md"], [], root=tmp_path)
        assert [f.message for f in findings] == ["script does not exist: scripts/after.py"]


def test_non_shell_fence_and_cd_arguments(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "````text\n```sh\npython3 scripts/display.py\n```\n````\n"
        '```sh\necho time cd subdir\necho "start;cd subdir;end"\npython3 scripts/missing.py\n```\n'
    )
    findings = gate.run_validate(["CLAUDE.md"], [], root=tmp_path)
    assert [f.message for f in findings] == ["script does not exist: scripts/missing.py"]
