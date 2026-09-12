"""Tests for scripts/check_skill_deps.py (issue #330)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

import check_skill_deps as deps  # noqa: E402

REPO_ROOT = SCRIPTS_DIR.parent


def _make_tmp_root(tmp_path: Path, skill_id: str, files: dict[str, str]) -> Path:
    root = tmp_path / "repo"
    skill_dir = root / "skills" / skill_id
    for rel, text in files.items():
        target = skill_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (root / "skills-index.yaml").write_text(
        f"skills:\n- id: {skill_id}\n  status: production\n", encoding="utf-8"
    )
    return root


def test_requirement_grammar_rejects_url_marker_duplicate(tmp_path: Path) -> None:
    manifest = tmp_path / "requirements.txt"
    manifest.write_text(
        "requests>=2.31.0\n"
        "pkg @ https://example.com/pkg.zip\n"
        "other>=1.0; python_version<'3.9'\n"
        "requests>=2.0\n"
        "bare-optional>=1.0  # optional:\n",
        encoding="utf-8",
    )
    entries, errors = deps.parse_requirements(manifest)
    # Rejected lines (URL, marker, duplicate) never become entries.
    assert set(entries) == {"requests", "bare-optional"}
    assert any("URL" in error for error in errors)
    assert any("markers" in error for error in errors)
    assert any("duplicate" in error for error in errors)
    assert any("needs a reason" in error for error in errors)


def test_requirement_extras_accepted(tmp_path: Path) -> None:
    manifest = tmp_path / "requirements.txt"
    manifest.write_text("somepkg[extra]>=1.0\n", encoding="utf-8")
    entries, errors = deps.parse_requirements(manifest)
    assert not errors
    assert entries["somepkg"].spec == "somepkg[extra]>=1.0"


def test_missing_manifest_fails_closed(tmp_path: Path) -> None:
    root = _make_tmp_root(tmp_path, "demo", {"scripts/run.py": "print('ok')\n"})
    report = deps.check_skill("demo", root, {})
    assert not report.ok
    assert any("missing requirements.txt" in e for e in report.errors)


def test_test_only_import_does_not_require_declaration(tmp_path: Path) -> None:
    """Scan root is packaged scripts/: tests/ imports are invisible (B2)."""
    root = _make_tmp_root(
        tmp_path,
        "demo",
        {
            "requirements.txt": "# stdlib-only\n",
            "scripts/run.py": "import json\nprint(json.dumps({}))\n",
            "scripts/tests/test_run.py": "import requests\ndef test_x(): pass\n",
        },
    )
    report = deps.check_skill("demo", root, {})
    assert report.ok, report.errors


def test_top_level_import_requires_declaration(tmp_path: Path) -> None:
    root = _make_tmp_root(
        tmp_path,
        "demo",
        {
            "requirements.txt": "# stdlib-only\n",
            "scripts/run.py": "import requests\nprint('ok')\n",
        },
    )
    report = deps.check_skill("demo", root, {})
    assert not report.ok
    assert any("undeclared" in e and "requests" in e for e in report.errors)


def test_nested_function_import_is_detected(tmp_path: Path) -> None:
    """Function-level lazy imports (fmp_client.py shape) are detected."""
    root = _make_tmp_root(
        tmp_path,
        "demo",
        {
            "requirements.txt": "requests>=2.31.0\n",
            "scripts/client.py": ("def fetch():\n    import yfinance as yf\n    return yf\n"),
        },
    )
    report = deps.check_skill("demo", root, {})
    assert not report.ok
    assert any("yfinance" in e for e in report.errors)


def test_stale_entry_fails(tmp_path: Path) -> None:
    root = _make_tmp_root(
        tmp_path,
        "demo",
        {
            "requirements.txt": "requests>=2.31.0\npandas>=2.0\n",
            "scripts/run.py": "import requests\nprint('ok')\n",
        },
    )
    report = deps.check_skill("demo", root, {})
    assert not report.ok
    assert any("stale" in e and "pandas" in e for e in report.errors)


def test_optional_without_fallback_fails(tmp_path: Path) -> None:
    root = _make_tmp_root(
        tmp_path,
        "demo",
        {
            "requirements.txt": "requests>=2.31.0  # optional: test reason\n",
            "scripts/run.py": "import requests\nprint('ok')\n",
        },
    )
    report = deps.check_skill("demo", root, {})
    assert not report.ok
    assert any("fallback" in e for e in report.errors)


def test_optional_without_absence_test_fails(tmp_path: Path) -> None:
    root = _make_tmp_root(
        tmp_path,
        "demo",
        {
            "requirements.txt": "requests>=2.31.0  # optional: test reason\n",
            "scripts/run.py": (
                "try:\n    import requests\n    HAS = True\nexcept ImportError:\n    HAS = False\n"
            ),
        },
    )
    report = deps.check_skill("demo", root, {})
    assert not report.ok
    assert any("absence test" in e for e in report.errors)


def test_optional_with_fallback_and_test_passes(tmp_path: Path) -> None:
    root = _make_tmp_root(
        tmp_path,
        "demo",
        {
            "requirements.txt": "requests>=2.31.0  # optional: test reason\n",
            "scripts/run.py": (
                "try:\n    import requests\n    HAS = True\nexcept ImportError:\n    HAS = False\n"
            ),
            "scripts/tests/test_run.py": "# absence path for requests\ndef test_x(): pass\n",
        },
    )
    report = deps.check_skill("demo", root, {})
    assert report.ok, report.errors
    assert report.optional == ["requests"]


def test_unmapped_third_party_import_fails_closed(tmp_path: Path) -> None:
    """Imports outside IMPORT_TO_DIST are errors, never silent passes."""
    root = _make_tmp_root(
        tmp_path,
        "demo",
        {
            "requirements.txt": "# stdlib-only\n",
            "scripts/run.py": "import sklearn\nprint('ok')\n",
        },
    )
    report = deps.check_skill("demo", root, {})
    assert not report.ok
    assert any("unmapped" in e and "sklearn" in e for e in report.errors)


def test_probe_dynamic_import_is_allowlisted() -> None:
    """The golden skill's startup probe warns nowhere (context allowlist)."""
    report = deps.check_skill("macro-regime-detector", REPO_ROOT)
    assert report.ok, report.errors
    assert report.warnings == []


def test_dynamic_import_warns_but_passes(tmp_path: Path) -> None:
    root = _make_tmp_root(
        tmp_path,
        "demo",
        {
            "requirements.txt": "# stdlib-only\n",
            "scripts/run.py": "mod = __import__('json')\nprint(mod)\n",
        },
    )
    report = deps.check_skill("demo", root, {})
    assert report.ok, report.errors
    assert any("dynamic import" in w for w in report.warnings)


def test_vendored_stdlib_has_no_modern_attribute_reference() -> None:
    source = (SCRIPTS_DIR / "check_skill_deps.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "stdlib_module_names"
        for node in ast.walk(tree)
    )
    for module in (
        "zoneinfo",
        "urllib",
        "http",
        "email",
        "importlib",
        "ast",
        "json",
        "subprocess",
        "shlex",
        "webbrowser",
        "msvcrt",
        "fcntl",
        "zoneinfo",
    ):
        assert module in deps.STDLIB_39
    # Guard against transcription drops in the vendored snapshot
    # (267 entries at authoring; private interpreter details omitted).
    assert len(deps.STDLIB_39) >= 267


def test_check_module_has_no_network_surface() -> None:
    """The PR-path check must not import networking/process modules."""
    source = (SCRIPTS_DIR / "check_skill_deps.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint({"subprocess", "socket", "urllib", "requests", "http", "ssl"})


def test_executable_inventory_reuses_ci_matrix() -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from ci_test_matrix import executable_test_inventory

        assert set(deps.executable_skill_ids()) == set(executable_test_inventory(REPO_ROOT))
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_pair_trade_statsmodels_bound_preserved() -> None:
    text = (REPO_ROOT / "skills" / "pair-trade-screener" / "requirements.txt").read_text(
        encoding="utf-8"
    )
    assert "statsmodels>=0.14,<0.15" in text


def test_real_tree_theme_detector_optionals_pass() -> None:
    report = deps.check_skill("theme-detector", REPO_ROOT)
    assert report.ok, report.errors
    assert set(report.optional) == {"finvizfinance", "yfinance"}


def test_real_tree_all_executable_skills_pass() -> None:
    for skill_id in deps.executable_skill_ids():
        report = deps.check_skill(skill_id, REPO_ROOT)
        assert report.ok, f"{skill_id}: {report.errors}"


def test_smoke_verifies_packaged_manifest(tmp_path: Path) -> None:
    skill_id = "macro-regime-detector"
    assert deps.run_smoke(skill_id, REPO_ROOT) == 0
    assert deps.run_smoke("no-such-skill", REPO_ROOT) == 1


def test_smoke_rejects_unsafe_skill_id() -> None:
    assert deps.run_smoke("../evil", REPO_ROOT) == 1
    assert deps.run_smoke("", REPO_ROOT) == 1
