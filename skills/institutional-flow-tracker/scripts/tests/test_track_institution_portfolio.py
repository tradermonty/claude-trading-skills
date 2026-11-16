"""The placeholder portfolio tracker keeps stdout empty and reports on stderr (#497)."""

import sys

import track_institution_portfolio as tip


def test_placeholder_writes_all_guidance_to_stderr_and_exits_1(monkeypatch, capsys):
    monkeypatch.setattr(
        sys, "argv", ["track_institution_portfolio.py", "--cik", "0001067983", "--name", "A B"]
    )
    assert tip.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR: This script is not yet functional" in captured.err
    assert "WhaleWisdom" in captured.err
    assert "CIK=0001067983" in captured.err
    assert "https://whalewisdom.com/filer/a-b" in captured.err


def test_import_has_no_output(capsys):
    # The guidance used to print at import time; it must not any more.
    import importlib

    importlib.reload(tip)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
