"""Exercise the warning gate in isolated pytest processes with flat imports."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "scripts/pytest_firstparty_warnings.py"


def run_case(tmp_path, source, *, collection=False, dependency=False, early=False):
    production = tmp_path / "skills" / "fictional" / "scripts"
    production.mkdir(parents=True)
    module_dir = tmp_path / "site-packages" if dependency else production
    module_dir.mkdir(exist_ok=True)
    (module_dir / "flat_module.py").write_text(source)
    test = tmp_path / "test_case.py"
    test.write_text(
        "import flat_module\ndef test_ok(): pass\n"
        if collection
        else "def test_ok():\n    import flat_module\n    flat_module.run()\n"
    )
    if early:
        (tmp_path / "conftest.py").write_text("import flat_module\n")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n")
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(module_dir)])
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--import-mode=importlib",
            "-c",
            str(ini),
            "-p",
            "scripts.pytest_firstparty_warnings",
            str(test),
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )


def test_flat_firstparty_deprecation_fails(tmp_path):
    result = run_case(
        tmp_path,
        "import warnings\ndef run():\n    warnings.warn('arbitrary debt', DeprecationWarning)\n",
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "First-party deprecations" in result.stdout
    assert "arbitrary debt" in result.stdout
    assert "INTERNALERROR" not in result.stdout


def test_collection_firstparty_deprecation_fails(tmp_path):
    result = run_case(
        tmp_path,
        "import warnings\nwarnings.warn('collection debt', DeprecationWarning)\n",
        collection=True,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "collection debt" in result.stdout


def test_dependency_deprecation_is_not_fatal(tmp_path):
    result = run_case(
        tmp_path,
        "import warnings\ndef run():\n    warnings.warn('dependency debt', DeprecationWarning)\n",
        dependency=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_expected_firstparty_deprecation_is_allowed(tmp_path):
    result = run_case(
        tmp_path,
        "import warnings\nimport pytest\ndef run():\n    with pytest.warns(DeprecationWarning):\n        warnings.warn('expected', DeprecationWarning)\n",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_initial_conftest_firstparty_deprecation_fails_cleanly(tmp_path):
    result = run_case(
        tmp_path,
        "import warnings\nwarnings.warn('early debt', DeprecationWarning)\n",
        early=True,
        collection=True,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "First-party deprecations" in result.stdout
    assert "early debt" in result.stdout
    assert "INTERNALERROR" not in result.stdout + result.stderr


def test_initial_conftest_dependency_deprecation_is_not_fatal(tmp_path):
    result = run_case(
        tmp_path,
        "import warnings\nwarnings.warn('early dependency', DeprecationWarning)\n",
        early=True,
        collection=True,
        dependency=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
