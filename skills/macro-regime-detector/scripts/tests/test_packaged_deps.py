"""Packaged-dependency contract for macro-regime-detector (issue #330).

Covers the #311 regression: a standalone install without ``yfinance``
must fail with an actionable message (exit 2 naming requirements.txt),
never with a silent all-zero report.
"""

import os
import subprocess
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import macro_regime_detector
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
SKILL_DIR = SCRIPTS_DIR.parent
REPO_ROOT = SKILL_DIR.parent.parent


def test_missing_package_exits_actionable(tmp_path, monkeypatch, capsys):
    """A missing required package exits 2 and names requirements.txt."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["macro_regime_detector.py", "--output-dir", str(tmp_path)],
    )
    with (
        patch.object(macro_regime_detector, "missing_required_packages", return_value=["yfinance"]),
        pytest.raises(SystemExit) as exc_info,
    ):
        macro_regime_detector.main()
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "yfinance" in err
    assert "requirements.txt" in err
    assert not list(tmp_path.rglob("macro_regime_*.json"))


def test_probe_ignores_present_packages():
    """Installed required packages are never reported missing."""
    assert "requests" not in macro_regime_detector.missing_required_packages()


def test_help_exits_zero():
    """--help works without credentials, network, or data packages."""
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "macro_regime_detector.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0


def test_broken_yfinance_install_exits_actionable(tmp_path):
    """A shadow yfinance.py raising ImportError exits 2 (issue #311 shape)."""
    stub_dir = tmp_path / "stubs"
    stub_dir.mkdir()
    (stub_dir / "yfinance.py").write_text('raise ImportError("no yfinance")\n', encoding="utf-8")
    env = dict(os.environ)
    env.pop("FMP_API_KEY", None)
    env["PYTHONPATH"] = str(stub_dir) + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "macro_regime_detector.py"),
            "--output-dir",
            str(tmp_path / "reports"),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert completed.returncode == 2
    assert "requirements.txt" in completed.stderr


def test_packaged_skill_declares_yfinance():
    """The committed .skill ships requirements.txt including yfinance."""
    archive = REPO_ROOT / "skill-packages" / "macro-regime-detector.skill"
    assert archive.is_file(), "packaged archive must be committed in this repo"
    with zipfile.ZipFile(archive) as bundle:
        name = "macro-regime-detector/requirements.txt"
        assert name in bundle.namelist()
        text = bundle.read(name).decode("utf-8")
    assert "yfinance" in text


def test_missing_requests_exits_actionable_before_import(tmp_path):
    """Blocking requests still yields exit 2 (not an import traceback).

    fmp_client imports requests at module top level; the guarded
    ``from fmp_client import FMPClient`` in macro_regime_detector defers
    that failure to the startup probe. --help must also survive it.
    """
    preamble = (
        "import sys; sys.modules['requests'] = None; "
        "sys.argv = ['macro_regime_detector.py', '--output-dir', r'{}']; ".format(
            tmp_path / "reports"
        )
        + "import macro_regime_detector; macro_regime_detector.main()"
    )
    completed = subprocess.run(
        [sys.executable, "-c", preamble],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(SCRIPTS_DIR),
    )
    assert completed.returncode == 2
    assert "requirements.txt" in completed.stderr

    help_preamble = (
        "import sys; sys.modules['requests'] = None; "
        "sys.argv = ['macro_regime_detector.py', '--help']; "
        "import macro_regime_detector; macro_regime_detector.main()"
    )
    completed_help = subprocess.run(
        [sys.executable, "-c", help_preamble],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(SCRIPTS_DIR),
    )
    assert completed_help.returncode == 0
