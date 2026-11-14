"""Behavioural tests for scripts/run_all_tests.sh using a fake ``uv`` on PATH."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

BASH = "/bin/bash"
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "run_all_tests.sh"

pytestmark = pytest.mark.skipif(not os.path.exists(BASH), reason="/bin/bash not available")

SKIP_LINE = (
    "SKIPPED [1] skills/x/test_a.py:3: could not import 'pyarrow': No module named 'pyarrow'"
)

FAKE_UV = r"""#!/bin/sh
# Fake uv: records argv, emulates the ci_test_matrix.py sub-commands.
echo "$*" >> "$FAKE_UV_LOG"
# Locate the sub-command: the argument right after ci_test_matrix.py.
cmd=""
seen=""
for a; do
    if [ -n "$seen" ] && [ -z "$cmd" ]; then cmd="$a"; fi
    case "$a" in *ci_test_matrix.py) seen=1 ;; esac
    id="$a"
done
case "$cmd" in
list)
    ids="${FAKE_ROW_IDS:-alpha\nbeta}"
    printf '%b\nCovered exclusions:\n  - none\n' "$ids"
    ;;
install)
    [ "$id" = "$FAKE_INSTALL_FAIL" ] && exit 1
    exit 0
    ;;
run)
    echo "pytest summary for $id"
    [ "$id" = "$FAKE_SKIP_ROW" ] && printf '%s\n' "$FAKE_SKIP_LINE"
    [ "$id" = "$FAKE_FAIL_ROW" ] && exit 1
    exit 0
    ;;
allowed-failure)
    [ "$id" = "$FAKE_ALLOWED_ROW" ] && exit 0
    exit 1
    ;;
esac
exit 0
"""


def _run(tmp_path: Path, **extra_env: str):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    uv = fake_bin / "uv"
    uv.write_text(FAKE_UV, encoding="utf-8")
    uv.chmod(uv.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "uv.log"
    log.write_text("", encoding="utf-8")
    private_tmp = tmp_path / "tmpdir"
    private_tmp.mkdir(exist_ok=True)
    env = {
        "TMPDIR": str(private_tmp),
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "FAKE_UV_LOG": str(log),
        "FAKE_SKIP_LINE": SKIP_LINE,
        **extra_env,
    }
    proc = subprocess.run(
        [BASH, str(SCRIPT)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc, log.read_text(encoding="utf-8").splitlines()


def test_skips_are_summarised_and_not_fatal(tmp_path):
    proc, _ = _run(tmp_path, FAKE_SKIP_ROW="beta")
    out = proc.stdout
    assert proc.returncode == 0, proc.stderr
    assert "=== Summary: 2/2 passed ===" in out
    assert "=== Skipped tests: 1 ===" in out
    assert f"beta: {SKIP_LINE}" in out
    assert (
        out.index("=== Summary") < out.index("=== Skipped tests") < out.index("Covered exclusions:")
    )


def test_zero_skips_works_under_bash_3_2_nounset(tmp_path):
    proc, _ = _run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "=== Skipped tests: 0 ===" in proc.stdout
    assert "unbound variable" not in proc.stderr


def test_failing_row_exits_1_and_still_prints_summary(tmp_path):
    proc, _ = _run(tmp_path, FAKE_FAIL_ROW="alpha", FAKE_SKIP_ROW="beta")
    assert proc.returncode == 1
    assert "=== Summary: 1/2 passed ===" in proc.stdout
    assert "=== Skipped tests: 1 ===" in proc.stdout
    assert f"beta: {SKIP_LINE}" in proc.stdout
    assert "FAILED: alpha" in proc.stdout
    assert proc.stdout.index("Covered exclusions:") < proc.stdout.index("FAILED: alpha")


def test_install_failure_exits_1_and_skips_run(tmp_path):
    proc, log = _run(tmp_path, FAKE_INSTALL_FAIL="alpha")
    assert proc.returncode == 1
    assert "FAILED: alpha" in proc.stdout
    assert not any(line.endswith("ci_test_matrix.py run alpha") for line in log)


def test_allowed_failure_row_is_non_blocking(tmp_path):
    proc, _ = _run(tmp_path, FAKE_FAIL_ROW="alpha", FAKE_ALLOWED_ROW="alpha")
    assert proc.returncode == 0
    assert "KNOWN FAILURE: alpha is non-blocking" in proc.stdout
    assert "=== Summary: 2/2 passed ===" in proc.stdout


def test_every_uv_call_uses_dev_and_ci_extras_and_install_check(tmp_path):
    _, log = _run(tmp_path)
    assert log
    for line in log:
        assert line.startswith("run --extra dev --extra ci "), line
    assert any("ci_test_matrix.py install --check alpha" in line for line in log)
    assert not any(line.endswith("ci_test_matrix.py install alpha") for line in log)


def test_skip_count_sums_pytest_group_counts(tmp_path):
    lines = "SKIPPED [3] skills/x/test_a.py:3: reason a\nSKIPPED [1] skills/y/test_b.py:9: reason b"
    proc, _ = _run(tmp_path, FAKE_SKIP_ROW="beta", FAKE_SKIP_LINE=lines)
    assert proc.returncode == 0, proc.stderr
    assert "=== Skipped tests: 4 ===" in proc.stdout
    assert "beta: SKIPPED [3] skills/x/test_a.py:3: reason a" in proc.stdout
    assert "beta: SKIPPED [1] skills/y/test_b.py:9: reason b" in proc.stdout


def test_row_id_with_sed_metacharacters_is_prefixed_verbatim(tmp_path):
    proc, _ = _run(
        tmp_path,
        FAKE_SKIP_ROW="al|pha&x",
        FAKE_SKIP_LINE="SKIPPED [1] a.py:1: r",
        FAKE_ROW_IDS="al|pha&x\nbeta",
    )
    assert proc.returncode == 0, proc.stderr
    assert "al|pha&x: SKIPPED [1] a.py:1: r" in proc.stdout


@pytest.mark.parametrize(
    "env",
    [{}, {"FAKE_FAIL_ROW": "alpha"}, {"FAKE_INSTALL_FAIL": "alpha"}],
    ids=["success", "failing-row", "install-failure"],
)
def test_temp_dir_is_removed_after_run(tmp_path, env):
    _run(tmp_path, FAKE_SKIP_ROW="beta", **env)
    assert list((tmp_path / "tmpdir").iterdir()) == []
