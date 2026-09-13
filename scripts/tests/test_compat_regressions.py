"""Cross-platform regression tests (issue #333).

These are platform-agnostic and exercise the failure classes that past bugs
introduced on Windows (#64 default-encoding Markdown failure) and the
standalone dependency gap (#311). They must pass on Linux, Windows, and macOS
under both the min and max supported Python. They need no paid APIs and no
network. Align with the policy in docs/dev/compatibility-matrix.md.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def test_utf8_write_and_read_no_locale_reliance(tmp_path: Path) -> None:
    """Write/read a Unicode file strictly as UTF-8 (guards #64)."""
    payload = "中央値 テスト 配当 ε μ — — “quotes”"
    target = tmp_path / "unicode.txt"
    target.write_text(payload, encoding="utf-8")
    assert target.read_text(encoding="utf-8") == payload
    with target.open("r", encoding="utf-8") as fh:
        assert fh.read() == payload


def test_newline_normalization_crlf(tmp_path: Path) -> None:
    """CRLF fixture normalizes to LF deterministically."""
    crlf = b"line1\r\nline2\r\nline3\r\n"
    target = tmp_path / "crlf.txt"
    target.write_bytes(crlf)
    text = target.read_text(encoding="utf-8", newline=None)
    normalized = text.replace("\r\n", "\n")
    assert normalized == "line1\nline2\nline3\n"
    assert "\r\n" not in normalized


def test_pathlib_join_both_separators(tmp_path: Path) -> None:
    """pathlib handles both separators; no hard-coded '/' assumptions."""
    nested = Path("a") / "b" / "c.txt"
    assert nested.parts == ("a", "b", "c.txt")
    os_joined = os.path.join("a", "b", "c.txt")
    if os.name == "nt":
        assert os_joined == "a\\b\\c.txt"
    else:
        assert os_joined == "a/b/c.txt"
    # Pure path interprets a forward-slash literal on any OS.
    assert Path("a/b/c.txt").parts == ("a", "b", "c.txt")


def test_tempdir_created_and_cleanup() -> None:
    """tempfile.TemporaryDirectory creates and cleans up without cwd leakage."""
    cwd_before = Path.cwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        assert path.is_dir()
        marker = path / "marker.txt"
        marker.write_text("x", encoding="utf-8")
        assert marker.read_text(encoding="utf-8") == "x"
        assert Path.cwd() == cwd_before
    assert not Path(tmpdir).exists()


def test_subprocess_arg_list_no_shell_true() -> None:
    """Invoke via arg list (no shell=True) and round-trip a spaced/quoting arg."""
    payload = "a b 'c' \"d\" $HOME ; |"
    result = subprocess.run(
        [sys.executable, "-c", "import sys; sys.stdout.write(sys.argv[1])", payload],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == payload
