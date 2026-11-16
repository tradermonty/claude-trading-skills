# Private thesis backup and restore drill

Run from the repository root using its Python environment (with PyYAML installed).
Stop **all writers** to the source until backup finishes; these checks do not lock
other processes or provide an atomic snapshot. Never run against an untrusted or
concurrently modified filesystem. This procedure reads private data locally; do
not paste its output, manifest, or backup into an Issue, PR, or model prompt.

Recommended operator cadence: take a fresh snapshot before migrations or bulk
state changes and at the end of each day that changes live thesis state. Keep
at least the last verified recovery point and an encrypted off-device copy;
repeat a restore drill after changing storage or the store format. This is a
manual policy, not a scheduled backup service. Review retention and revoke
obsolete copies separately.

The defaults below preserve `state/theses`. Journals under `state/journal` need a
separate backup and validation procedure. This is a recovery drill, not automatic
retention, encryption, authentication, or replacement of live state. Use encrypted
storage for off-device copies and restrict OS access. SHA-256 detects accidental
corruption; an attacker who changes both data and manifest can defeat it.

Execute the **helpers** block, then **backup** in the same Python session. For a
later recovery, start a new session and execute **helpers**, then **restore** only;
the original source need not exist. Change the snapshot name for each new backup.
A failure can leave a partial directory: preserve it privately for investigation,
choose a fresh name on retry, and never treat it as a completed backup. No files
are automatically removed by this recipe.

<!-- recipe: helpers -->
```python
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

SOURCE = Path("state/theses")
PRIVATE = Path("private-backups")
BACKUP = PRIVATE / "theses-snapshot"
MANIFEST = PRIVATE / "theses-snapshot.sha256.json"
RESTORED = PRIVATE / "theses-restored"
STORE = Path("skills/trader-memory-core/scripts/thesis_store.py")


def checked(path, directory=False):
    # lstat every existing ancestor, including dangling links; never resolve them.
    for entry in [*reversed(path.parents), path]:
        if entry == Path("."):
            continue
        mode = entry.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError("Symlink boundary refused")
        if entry != path or directory:
            if not stat.S_ISDIR(mode):
                raise ValueError("Directory required")
        elif not stat.S_ISREG(mode):
            raise ValueError("Regular file required")


def fresh(path):
    checked(path.parent, directory=True)
    if os.path.lexists(path):
        raise ValueError("Destination already exists")


def private_parent():
    if not os.path.lexists(PRIVATE):
        PRIVATE.mkdir(mode=0o700)
    checked(PRIVATE, directory=True)
    if os.name == "posix" and PRIVATE.stat().st_mode & 0o077:
        raise ValueError("Private parent must deny group/other access")
    # On Windows, operator must configure and verify a restrictive ACL first.


def digests(root):
    checked(root, directory=True)
    result = {}
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            checked(path, directory=True)
        else:
            checked(path)
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def doctor(root):
    subprocess.run(
        [sys.executable, str(STORE), "--state-dir", str(root), "doctor"],
        check=True, capture_output=True, timeout=60,
    )
```

On Windows, create `private-backups` with an ACL limited to the operator before
running either phase. POSIX mode checks cover the private parent, not the security
of your account, disk, or remote backup service. Paths here must remain relative
to a trusted repository root; do not change them to symlinks.

<!-- recipe: backup -->
```python
private_parent()
fresh(BACKUP)
fresh(MANIFEST)
before = digests(SOURCE)
doctor(SOURCE)
shutil.copytree(SOURCE, BACKUP)
if before != digests(SOURCE) or before != digests(BACKUP):
    raise ValueError("Source changed or backup differs; no success manifest")
doctor(BACKUP)
with MANIFEST.open("x", encoding="utf-8") as stream:
    json.dump(before, stream, sort_keys=True, indent=2)
```

<!-- recipe: restore -->
```python
private_parent()
fresh(RESTORED)
checked(MANIFEST)
expected = json.loads(MANIFEST.read_text(encoding="utf-8"))
if not isinstance(expected, dict) or expected != digests(BACKUP):
    raise ValueError("Backup file list or hashes differ from manifest")
shutil.copytree(BACKUP, RESTORED)
if expected != digests(RESTORED):
    raise ValueError("Restored file list or hashes differ")
doctor(RESTORED)
```

Success means the copied file set and bytes match the saved manifest and the
store's read-only `doctor` accepts the copy. It does not prove trading correctness
or back up credentials and broker state. Inspect the copy locally, retain the
original snapshot, and only then decide whether to point a future command's
`--state-dir` at the recovered directory. The recipe never promotes or overwrites
live state. Delete old private copies only after a separate retention review.

`scripts/tests/test_thesis_backup_recipe.py` executes these exact blocks against
fictional theses, removes only the fixture source, and restores in a fresh Python
namespace. It also exercises tampering, file additions/deletions, occupied
outputs, unsafe permissions, symlinks and a changing source. This is local
synthetic verification, not evidence that any user's backup has been restored.
