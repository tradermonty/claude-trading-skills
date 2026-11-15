"""Execute the published recovery recipe on fictional state, never user data."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/dev/thesis-backup-restore.md"
BLOCKS = dict(re.findall(r"<!-- recipe: (\w+) -->\n```python\n(.*?)\n```", DOC.read_text(), re.S))


@pytest.fixture
def recipe(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Only fixture source/output paths are copied or removed.
    namespace = {}
    exec(BLOCKS["helpers"], namespace)
    namespace["STORE"] = ROOT / "skills/trader-memory-core/scripts/thesis_store.py"
    source = tmp_path / "state/theses"
    program = """
import sys
sys.path.insert(0, sys.argv[1])
import thesis_store
from pathlib import Path
thesis_store.register(Path(sys.argv[2]), {
    'ticker': 'DEMO', 'thesis_type': 'dividend_income',
    'thesis_statement': 'Fictional recovery test',
    'origin': {'skill': 'test', 'output_file': 'fictional.json'},
})
"""
    subprocess.run(
        [sys.executable, "-c", program, str(namespace["STORE"].parent), str(source)],
        check=True,
        capture_output=True,
    )
    return namespace


def run(phase, namespace):
    exec(BLOCKS[phase], namespace)


def test_restore_without_original_in_fresh_session(recipe):
    before = recipe["digests"](recipe["SOURCE"])
    run("backup", recipe)
    assert recipe["digests"](recipe["SOURCE"]) == before
    shutil.rmtree(recipe["SOURCE"])
    fresh = {}
    exec(BLOCKS["helpers"], fresh)
    fresh["STORE"] = recipe["STORE"]
    run("restore", fresh)
    assert fresh["digests"](fresh["RESTORED"]) == before
    assert json.loads(fresh["MANIFEST"].read_text()) == before
    assert not fresh["SOURCE"].exists()


@pytest.mark.parametrize("change", ["tamper", "add", "delete"])
def test_corrupted_backup_refused_before_restore(recipe, change):
    run("backup", recipe)
    target = next(recipe["BACKUP"].glob("*.yaml"))
    if change == "tamper":
        target.write_text("corrupt")
    elif change == "add":
        (recipe["BACKUP"] / "extra").write_text("extra")
    else:
        target.unlink()
    with pytest.raises(ValueError, match="differ"):
        run("restore", recipe)
    assert not recipe["RESTORED"].exists()


@pytest.mark.parametrize("occupied", ["BACKUP", "MANIFEST", "RESTORED"])
def test_occupied_destination_never_overwritten(recipe, occupied):
    if occupied == "RESTORED":
        run("backup", recipe)
    else:
        recipe["private_parent"]()
    recipe[occupied].write_text("keep")
    with pytest.raises(ValueError, match="already exists"):
        run("restore" if occupied == "RESTORED" else "backup", recipe)
    assert recipe[occupied].read_text() == "keep"


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
def test_unsafe_parent_refused(recipe):
    recipe["PRIVATE"].mkdir(mode=0o755)
    recipe["PRIVATE"].chmod(0o755)
    with pytest.raises(ValueError, match="group/other"):
        run("backup", recipe)


@pytest.mark.parametrize("boundary", ["source", "file", "private", "destination"])
def test_links_refused(recipe, boundary, tmp_path):
    try:
        if boundary == "source":
            recipe["SOURCE"].rename("real-source")
            recipe["SOURCE"].symlink_to(tmp_path / "real-source", target_is_directory=True)
        elif boundary == "file":
            (recipe["SOURCE"] / "link").symlink_to("absent")
        elif boundary == "private":
            (tmp_path / "other").mkdir()
            recipe["PRIVATE"].symlink_to(tmp_path / "other", target_is_directory=True)
        else:
            recipe["private_parent"]()
            recipe["BACKUP"].symlink_to("absent")
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(ValueError):
        run("backup", recipe)
    assert not recipe["MANIFEST"].exists()


def test_source_changes_produce_no_success_manifest(recipe, monkeypatch):
    original = shutil.copytree

    def changing_copy(source, destination):
        result = original(source, destination)
        (source / "changed").write_text("concurrent write")
        return result

    monkeypatch.setattr(shutil, "copytree", changing_copy)
    with pytest.raises(ValueError, match="Source changed"):
        run("backup", recipe)
    assert not recipe["MANIFEST"].exists()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO unavailable")
def test_special_file_refused_before_copy(recipe):
    os.mkfifo(recipe["SOURCE"] / "pipe")
    with pytest.raises(ValueError, match="Regular file"):
        run("backup", recipe)
    assert not recipe["BACKUP"].exists()
    assert not recipe["MANIFEST"].exists()


def test_restore_rejects_linked_manifest(recipe):
    run("backup", recipe)
    recipe["MANIFEST"].rename("manifest-save.json")
    try:
        recipe["MANIFEST"].symlink_to(Path.cwd() / "manifest-save.json")
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(ValueError, match="Symlink"):
        run("restore", recipe)
    assert not recipe["RESTORED"].exists()


def test_existing_empty_state_can_be_recovered(recipe):
    shutil.rmtree(recipe["SOURCE"])
    recipe["SOURCE"].mkdir()
    run("backup", recipe)
    shutil.rmtree(recipe["SOURCE"])
    run("restore", recipe)
    assert recipe["digests"](recipe["RESTORED"]) == {}
