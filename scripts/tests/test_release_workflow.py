"""Publishing must stay behind tag, ancestry, and remote-byte gates."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_release_workflow_is_tag_only_and_fail_closed() -> None:
    workflow = yaml.load(
        (ROOT / ".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert workflow["on"] == {"push": {"tags": ["v*", "!v*-*"]}}
    assert workflow["concurrency"] == {"group": "release", "cancel-in-progress": "false"}
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["release"]
    assert job["permissions"] == {"contents": "write"}
    assert job["runs-on"] == "ubuntu-latest"
    steps = job["steps"]
    assert all(
        len(step["uses"].split("@", 1)[1].split(" ")[0]) == 40 for step in steps if "uses" in step
    )
    runs = "\n".join(step.get("run", "") for step in steps)
    for required in (
        "git merge-base --is-ancestor",
        "git ls-remote --refs origin",
        "release_assets.py prepare",
        "gh release create",
        "--draft --verify-tag",
        "gh release download",
        "release_assets.py verify",
        "release_assets.py latest-flag",
        "gh release list --exclude-drafts",
        'gh release edit "$RELEASE_TAG" --draft=false "$latest_flag"',
    ):
        assert required in runs
    commands = (
        "git merge-base --is-ancestor",
        "gh release create",
        "gh release download",
        "release_assets.py verify",
        'gh release edit "$RELEASE_TAG" --draft=false "$latest_flag"',
    )
    positions = [runs.index(command) for command in commands]
    assert positions == sorted(positions)
    assert 1 <= int(job["timeout-minutes"]) <= 15
    assert job["env"]["RELEASE_TAG"] == "${{ github.ref_name }}"
    for step in steps:
        if "run" in step:
            assert step["shell"] == "bash"
            assert step["run"].splitlines()[0] == "set -euo pipefail"
            assert "${{" not in step["run"]
    list_lines = [line for line in runs.splitlines() if "gh release list" in line]
    assert len(list_lines) == 1
    list_line = list_lines[0]
    assert "--exclude-drafts" in list_line
    # gh defaults to 30 rows; a truncated listing could re-mark an old tag latest.
    assert "--limit 1000" in list_line
    assert "--json tagName --jq '.[].tagName'" in list_line
    # Keep the listing out of the checkout so no later glob or upload picks it up.
    assert list_line.endswith('> "$RUNNER_TEMP/published-tags.txt"')
    flag_line = next(line for line in runs.splitlines() if "latest-flag" in line)
    assert flag_line.strip().startswith('latest_flag="$(python scripts/release_assets.py')
    assert '--published-tags-file "$RUNNER_TEMP/published-tags.txt"' in flag_line
    for line in runs.splitlines():
        if line in list_lines:
            continue
        if "gh release " in line or "prepare --tag" in line:
            assert '"$RELEASE_TAG"' in line
    text = (ROOT / ".github/workflows/release.yml").read_text()
    assert "--latest" not in text.replace("latest-flag", "")
    assert "--draft --verify-tag" in runs


def test_release_workflow_guards_cannot_be_bypassed() -> None:
    workflow = yaml.load(
        (ROOT / ".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader
    )
    steps = workflow["jobs"]["release"]["steps"]
    runs = "\n".join(step.get("run", "") for step in steps)
    for line in runs.splitlines():
        # set -e ignores failures of non-final commands in && / || lists.
        assert "&& test" not in line and "|| true" not in line
        if line.strip().startswith("test "):
            assert "&&" not in line and "||" not in line
    edit = runs.index('gh release edit "$RELEASE_TAG" --draft=false "$latest_flag"')
    edit_line = next(line for line in runs.splitlines() if "gh release edit" in line)
    assert edit_line.endswith('--draft=false "$latest_flag"')
    remote_checks = [i for i in range(len(runs)) if runs.startswith("git ls-remote --refs", i)]
    assert len(remote_checks) == 2
    assert runs.index("gh release download") < remote_checks[1] < edit
    assert runs.index("--json isDraft") < edit
    list_at = runs.index("gh release list --exclude-drafts")
    assert remote_checks[1] < list_at < runs.index("release_assets.py latest-flag") < edit
    assert runs.index("release_assets.py prepare") < runs.index("git merge-base --is-ancestor")
    assert runs.index("Release already exists") < runs.index("gh release create")
    lines = [line.strip() for line in runs.splitlines()]
    exists = next(i for i, line in enumerate(lines) if "Release already exists" in line)
    assert lines[exists + 1] == "exit 1"


def test_release_procedure_steps_are_separate_list_items() -> None:
    doc = (ROOT / "docs/dev/release-compatibility.md").read_text(encoding="utf-8")
    section = doc.split("## Release procedure", 1)[1].split("\n## ", 1)[0]
    items = [line for line in section.splitlines() if line[:1].isdigit()]
    assert [line.split(".", 1)[0] for line in items] == ["1", "2", "3", "4", "5"]
