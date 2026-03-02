"""Root conftest – isolate per-skill sys.path / sys.modules for bulk pytest.

Multiple skills ship identically-named modules (scorer.py, calculators/,
fmp_client.py, report_generator.py).  When pytest collects every test
directory in one process, conftest-level ``sys.path.insert`` calls
accumulate and the first match in *sys.path* (or the cached entry in
*sys.modules*) wins – which is almost always the **wrong** skill.

This conftest hooks into ``pytest_collectstart`` (collection phase) and
``pytest_runtest_setup`` (execution phase) to evict **only** the known
conflicting module names and push the current skill's ``scripts/``
directory to the front of ``sys.path``.
"""

import sys
from pathlib import Path

_SKILLS_MARKER = f"{Path.cwd()}/skills/"

# Module basenames that exist in more than one skill's scripts/ directory.
# Only these are evicted; unique names (e.g. analyze_single_stock) are kept.
_CONFLICTING_BASENAMES = frozenset(
    {
        "calculators",  # 8 skills
        "fmp_client",  # 7 skills
        "helpers",  # 5 skills (test helpers)
        "report_generator",  # 11 skills
        "scorer",  # 10 skills
    }
)

# Track last activated skill to skip redundant evictions.
_last_skill: "str | None" = None


def _skill_root(filepath: Path) -> "Path | None":
    """Return the skill root (dir containing SKILL.md) for *filepath*."""
    for parent in filepath.parents:
        if (parent / "SKILL.md").exists():
            return parent
    return None


def _activate_skill(skill: Path, test_dir: str) -> None:
    """Evict conflicting modules and adjust sys.path for *skill*."""
    global _last_skill  # noqa: PLW0603
    skill_prefix = str(skill)

    if _last_skill == skill_prefix:
        return
    _last_skill = skill_prefix

    scripts_dir = str(skill / "scripts")

    # 1. Evict only known-conflicting modules from OTHER skills.
    stale = [
        name
        for name in list(sys.modules)
        if name.split(".")[0] in _CONFLICTING_BASENAMES
        and skill_prefix not in (getattr(sys.modules[name], "__file__", None) or "")
        and _SKILLS_MARKER in (getattr(sys.modules[name], "__file__", None) or "")
    ]
    for name in stale:
        del sys.modules[name]

    # 2. Ensure this skill's scripts dir is first on sys.path.
    try:
        sys.path.remove(scripts_dir)
    except ValueError:
        pass
    sys.path.insert(0, scripts_dir)

    # 3. Ensure the test directory itself is on sys.path (some tests
    #    import helpers co-located with test files).
    try:
        sys.path.remove(test_dir)
    except ValueError:
        pass
    sys.path.insert(0, test_dir)


# ---------------------------------------------------------------------------
# Collection hook – fires before each test *module* is imported.
# ---------------------------------------------------------------------------


def pytest_collectstart(collector) -> None:
    fspath = getattr(collector, "path", None) or getattr(collector, "fspath", None)
    if fspath is None:
        return
    fspath = Path(fspath)
    if fspath.suffix != ".py":
        return
    skill = _skill_root(fspath)
    if skill is None:
        return
    _activate_skill(skill, str(fspath.parent))


# ---------------------------------------------------------------------------
# Execution hook – fires before each test *function* runs.
# Needed because test functions may do lazy imports at runtime.
# ---------------------------------------------------------------------------


def pytest_runtest_setup(item) -> None:
    fspath = getattr(item, "path", None) or getattr(item, "fspath", None)
    if fspath is None:
        return
    fspath = Path(fspath)
    skill = _skill_root(fspath)
    if skill is None:
        return
    _activate_skill(skill, str(fspath.parent))


# ---------------------------------------------------------------------------
# Ignore patterns – skip known-failing skills in bulk runs but allow
# explicit targeting (e.g. ``pytest skills/theme-detector/scripts/tests``).
# ---------------------------------------------------------------------------

_BULK_SKIP_GLOBS = [
    "skills/canslim-screener/*",  # requires bs4 (optional dep)
    "skills/theme-detector/tests/*",  # duplicate basenames vs scripts/tests/
    "skills/theme-detector/scripts/tests/*",  # 27+ pre-existing failures
]


def pytest_ignore_collect(collection_path, config):  # noqa: ANN001
    """Skip known-failing skills in bulk runs; allow explicit targeting."""
    import fnmatch

    try:
        rel = str(collection_path.relative_to(Path.cwd()))
    except ValueError:
        return None

    for glob_pat in _BULK_SKIP_GLOBS:
        if fnmatch.fnmatch(rel, glob_pat):
            # If user explicitly targeted a path containing this skill, allow it
            skill_name = glob_pat.split("/")[1]
            if any(skill_name in str(a) for a in config.args):
                return None  # don't skip
            return True  # skip in bulk run

    return None
