"""Publishing must stay behind tag, ancestry, and remote-byte gates."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_release_workflow_is_tag_only_and_fail_closed() -> None:
    workflow = yaml.load(
        (ROOT / ".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert workflow["on"] == {"push": {"tags": ["v*"]}}
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
        'gh release edit "$RELEASE_TAG" --draft=false',
    ):
        assert required in runs
    assert runs.index("release_assets.py verify") < runs.index(
        'gh release edit "$RELEASE_TAG" --draft=false'
    )
