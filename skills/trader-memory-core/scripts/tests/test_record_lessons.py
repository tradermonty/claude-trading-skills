"""Tests for the `store record-lessons` subcommand and record_lessons() (Issue #701)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import thesis_review as review
import thesis_store as store
import yaml

STORE_PY = Path(store.__file__).resolve()
REVIEW_PY = Path(review.__file__).resolve()
DATE = "2026-01-01T00:00:00+00:00"
END = "2026-01-02T00:00:00+00:00"


def _data(ticker="TEST", **overrides):
    result = {
        "ticker": ticker,
        "thesis_type": "pivot_breakout",
        # Non-ASCII on purpose: it is part of the fingerprint and stored in the YAML file.
        "thesis_statement": f"Synthetic {ticker} 決算",
        "origin": {"skill": "test", "output_file": "fixture.json"},
        "_source_date": "2026-01-01",
        "entry": {"target_price": 100},
        "exit": {"stop_loss": 90},
    }
    result.update(overrides)
    return result


def _ready(state, ticker="TEST"):
    tid = store.register(state, _data(ticker))
    store.transition(state, tid, "ENTRY_READY", "synthetic ready", event_date=DATE)
    return tid


def _active(state, ticker="TEST"):
    tid = _ready(state, ticker)
    store.open_position(state, tid, 100, DATE, shares=10, event_date=DATE)
    return tid


def _closed(state, ticker="TEST"):
    tid = _active(state, ticker)
    store.close(state, tid, "manual", 120, END)
    return tid


def _snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _cli(state, *args):
    proc = subprocess.run(
        [sys.executable, str(STORE_PY), "--state-dir", str(state), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _record(state, tid, *args):
    return _cli(state, "record-lessons", tid, *args)


def _lessons(state, tid):
    thesis = yaml.safe_load((state / f"{tid}.yaml").read_text(encoding="utf-8"))
    return thesis["outcome"]["lessons_learned"]


def _assert_clean_error(rc, err, *, contains=None):
    assert rc == 1, err
    assert err.startswith("ERROR:") or "\nERROR:" in err
    assert "Traceback" not in err
    if contains:
        assert contains in err


def test_record_text_on_closed_thesis(tmp_path):
    state = tmp_path / "theses"
    tid = _closed(state)
    path = state / f"{tid}.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["updated_at"] = "2026-01-02T00:00:00+00:00"  # timestamps have 1s resolution
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    before = store.get(state, tid)
    rc, out, err = _record(state, tid, "--text", "  Sized too big on the gap.  ")
    assert rc == 0, err
    assert f"{tid} lessons recorded (" in out
    assert "action=new" in out
    assert f"review postmortem {tid}" in out
    after = store.get(state, tid)
    assert after["outcome"]["lessons_learned"] == "Sized too big on the gap."
    assert after["updated_at"] != before["updated_at"]
    for field in ("pnl_dollars", "pnl_pct", "holding_days"):
        assert after["outcome"][field] == before["outcome"][field]
    rc, doc_out, _ = _cli(state, "doctor")
    assert rc == 0
    assert '"ok": true' in doc_out.lower() or "[]" in doc_out


def test_postmortem_shows_recorded_lessons(tmp_path):
    state = tmp_path / "theses"
    tid = _closed(state)
    journal = tmp_path / "journal"
    args = [sys.executable, str(REVIEW_PY), "--state-dir", str(state)]
    subprocess.run(
        [*args, "postmortem", tid, "--journal-dir", str(journal)], check=True, capture_output=True
    )
    assert "(not yet recorded)" in (journal / f"pm_{tid}.md").read_text(encoding="utf-8")
    rc, _, err = _record(state, tid, "--text", "Cut losers faster.")
    assert rc == 0, err
    subprocess.run(
        [*args, "postmortem", tid, "--journal-dir", str(journal)], check=True, capture_output=True
    )
    content = (journal / f"pm_{tid}.md").read_text(encoding="utf-8")
    assert "Cut losers faster." in content
    assert "(not yet recorded)" not in content


@pytest.mark.parametrize("bom", [False, True])
def test_file_japanese_utf8_round_trip(tmp_path, bom):
    state = tmp_path / "theses"
    tid = _closed(state)
    text = "決算後のギャップで買い急いだ。損切りを守る。"
    path = tmp_path / "lesson.txt"
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + (text + "\n").encode("utf-8"))
    rc, _, err = _record(state, tid, "--file", str(path))
    assert rc == 0, err
    assert _lessons(state, tid) == text
    rc, out, err = _cli(state, "get", tid)
    assert rc == 0, err
    assert yaml.safe_load(out)["outcome"]["lessons_learned"] == text
    rc, _, err = _cli(state, "rebuild-index")
    assert rc == 0, err


@pytest.mark.parametrize("stage", ["IDEA", "ENTRY_READY", "ACTIVE", "PARTIALLY_CLOSED"])
def test_non_terminal_status_rejected(tmp_path, stage):
    state = tmp_path / "theses"
    if stage == "IDEA":
        tid = store.register(state, _data())
    elif stage == "ENTRY_READY":
        tid = _ready(state)
    elif stage == "ACTIVE":
        tid = _active(state)
    else:
        tid = _active(state)
        store.trim(state, tid, 5, 120, END, "synthetic trim")
    before = _snapshot(state)
    rc, _, err = _record(state, tid, "--text", "too early")
    _assert_clean_error(rc, err, contains=stage)
    assert _snapshot(state) == before


def test_invalidated_allowed(tmp_path):
    state = tmp_path / "theses"
    tid = _active(state)
    store.terminate(state, tid, "INVALIDATED", "thesis broke")
    rc, _, err = _record(state, tid, "--text", "Thesis broke on guidance.")
    assert rc == 0, err
    assert _lessons(state, tid) == "Thesis broke on guidance."


def test_existing_value_modes(tmp_path):
    state = tmp_path / "theses"
    tid = _closed(state)
    assert _record(state, tid, "--text", "first")[0] == 0

    before = _snapshot(state)
    rc, _, err = _record(state, tid, "--text", "second")
    _assert_clean_error(rc, err)
    assert "--append" in err and "--replace" in err
    assert _snapshot(state) == before

    rc, out, err = _record(state, tid, "--text", "second", "--append")
    assert rc == 0, err
    assert "action=append" in out
    assert _lessons(state, tid) == "first\nsecond"
    expected_total = len("first\nsecond")
    assert f"({expected_total} chars" in out

    rc, out, err = _record(state, tid, "--text", "third", "--replace")
    assert rc == 0, err
    assert "action=replace" in out
    assert _lessons(state, tid) == "third"


def test_library_modes(tmp_path):
    state = tmp_path / "theses"
    tid = _closed(state)
    thesis, action = store.record_lessons(state, tid, "one")
    assert action == "new"
    assert thesis["outcome"]["lessons_learned"] == "one"
    before = _snapshot(state)
    with pytest.raises(ValueError, match="--append"):
        store.record_lessons(state, tid, "two", mode="error")
    assert _snapshot(state) == before
    with pytest.raises(ValueError, match="mode"):
        store.record_lessons(state, tid, "two", mode="bogus")
    assert _snapshot(state) == before
    _, action = store.record_lessons(state, tid, "two", mode="append")
    assert action == "append"
    _, action = store.record_lessons(state, tid, "three", mode="replace")
    assert action == "replace"


@pytest.mark.parametrize("text", ["", "   \n\t "])
def test_empty_text_rejected(tmp_path, text):
    state = tmp_path / "theses"
    tid = _closed(state)
    before = _snapshot(state)
    rc, _, err = _record(state, tid, "--text", text)
    _assert_clean_error(rc, err)
    assert _snapshot(state) == before


def test_length_limit(tmp_path):
    state = tmp_path / "theses"
    tid = _closed(state)
    before = _snapshot(state)
    rc, _, err = _record(state, tid, "--text", "x" * 10_001)
    _assert_clean_error(rc, err)
    assert _snapshot(state) == before
    rc, out, err = _record(state, tid, "--text", "x" * 10_000)
    assert rc == 0, err
    assert "(10000 chars" in out


def test_argparse_exclusive_groups(tmp_path):
    state = tmp_path / "theses"
    tid = _closed(state)
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    assert _record(state, tid, "--text", "a", "--file", str(f))[0] == 2
    assert _record(state, tid)[0] == 2
    assert _record(state, tid, "--text", "a", "--append", "--replace")[0] == 2


def test_unknown_id(tmp_path):
    state = tmp_path / "theses"
    state.mkdir()
    rc, _, err = _record(state, "th_nope_20260101_aaaa", "--text", "x")
    _assert_clean_error(rc, err, contains="th_nope_20260101_aaaa")


def test_file_errors_name_path(tmp_path):
    state = tmp_path / "theses"
    tid = _closed(state)
    before = _snapshot(state)
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"\xff\xfe\xfa invalid")
    for path in (tmp_path, tmp_path / "missing.txt", bad):
        rc, _, err = _record(state, tid, "--file", str(path))
        _assert_clean_error(rc, err, contains=str(path))
    assert _snapshot(state) == before


def test_whitespace_only_stored_value_counts_as_new(tmp_path):
    state = tmp_path / "theses"
    tid = _closed(state)
    store.update(state, tid, {"outcome": {"lessons_learned": "   "}})
    rc, out, err = _record(state, tid, "--text", "fresh")
    assert rc == 0, err
    assert "action=new" in out
    assert _lessons(state, tid) == "fresh"


def test_dash_leading_text_with_equals(tmp_path):
    state = tmp_path / "theses"
    tid = _closed(state)
    rc, _, err = _record(state, tid, "--text=-x")
    assert rc == 0, err
    assert _lessons(state, tid) == "-x"


def test_monthly_report_top_lessons(tmp_path):
    state = tmp_path / "theses"
    tid = _closed(state, "ZZZ")
    assert _record(state, tid, "--text", "first lesson")[0] == 0
    out_path = tmp_path / "monthly.md"
    cmd = [sys.executable, str(REVIEW_PY), "--state-dir", str(state)]
    subprocess.run(
        [*cmd, "monthly-report", "--month", "2026-01", "--output", str(out_path)],
        check=True,
        capture_output=True,
    )
    assert "- ZZZ: first lesson" in out_path.read_text(encoding="utf-8")
    assert _record(state, tid, "--text", "second lesson", "--append")[0] == 0
    subprocess.run(
        [*cmd, "monthly-report", "--month", "2026-01", "--output", str(out_path)],
        check=True,
        capture_output=True,
    )
    assert "- ZZZ: first lesson\nsecond lesson" in out_path.read_text(encoding="utf-8")


def test_find_by_fingerprint_skips_non_utf8_file(tmp_path):
    state = tmp_path / "theses"
    state.mkdir()
    (state / "th_bad_20260101_aaaa.yaml").write_bytes(b"ticker: \xff\xfe\xfa\n")
    tid = store.register(state, _data())
    assert tid.startswith("th_")


def test_legacy_short_closed_thesis_refused(tmp_path):
    state = tmp_path / "theses"
    tid = _closed(state)
    path = state / f"{tid}.yaml"
    thesis = yaml.safe_load(path.read_text(encoding="utf-8"))
    thesis["position"]["direction"] = "SHORT"
    path.write_text(yaml.safe_dump(thesis, sort_keys=False), encoding="utf-8")
    before = _snapshot(state)
    rc, _, err = _record(state, tid, "--text", "lesson")
    _assert_clean_error(rc, err, contains="long-only")
    assert _snapshot(state) == before


def test_surrogate_in_text_rejected(tmp_path):
    """Inject surrogate text after process startup so every OS tests the CLI handler."""
    state = tmp_path / "theses"
    tid = _closed(state)
    before = _snapshot(state)
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import runpy, sys; "
            "from pathlib import Path; "
            "script, state, tid = sys.argv[1:]; "
            "sys.path.insert(0, str(Path(script).parent)); "
            "sys.argv = [script, '--state-dir', state, 'record-lessons', tid, "
            "'--text', 'bad\\udcff']; "
            "runpy.run_path(script, run_name='__main__')",
            str(STORE_PY),
            str(state),
            tid,
        ],
        capture_output=True,
        timeout=60,
    )
    err = proc.stderr.decode("utf-8", "replace")
    _assert_clean_error(proc.returncode, err, contains="UTF-8")
    assert _snapshot(state) == before


@pytest.mark.skipif(os.name == "nt", reason="Invalid byte argv uses POSIX surrogateescape")
def test_posix_invalid_byte_argv_rejected(tmp_path):
    state = tmp_path / "theses"
    tid = _closed(state)
    before = _snapshot(state)
    proc = subprocess.run(
        [
            sys.executable.encode(),
            str(STORE_PY).encode(),
            b"--state-dir",
            str(state).encode(),
            b"record-lessons",
            tid.encode(),
            b"--text",
            b"bad\xff",
        ],
        capture_output=True,
        timeout=60,
    )
    err = proc.stderr.decode("utf-8", "replace")
    _assert_clean_error(proc.returncode, err, contains="UTF-8")
    assert _snapshot(state) == before


@pytest.mark.parametrize("text", ["a\x85b", "a\x85b c"])
def test_yaml_unsafe_characters_rejected(tmp_path, text):
    state = tmp_path / "theses"
    tid = _closed(state)
    before = _snapshot(state)
    rc, _, err = _record(state, tid, "--text", text)
    _assert_clean_error(rc, err, contains="round-trip")
    assert _snapshot(state) == before


def test_reported_length_matches_stored_for_special_chars(tmp_path):
    state = tmp_path / "theses"
    tid = _closed(state)
    text = "tab\there   crlf\r\nend \U0001f600"
    rc, out, err = _record(state, tid, "--text", text)
    assert rc == 0, err
    stored = _lessons(state, tid)
    assert f"({len(stored)} chars" in out
    assert stored == text.strip()


def test_append_enforces_total_cap(tmp_path):
    state = tmp_path / "theses"
    tid = _closed(state)
    assert _record(state, tid, "--text", "a" * 9000)[0] == 0
    before = _snapshot(state)
    rc, _, err = _record(state, tid, "--text", "b" * 9000, "--append")
    _assert_clean_error(rc, err, contains="total")
    assert _snapshot(state) == before


def test_append_to_unroundtrippable_stored_value_blames_stored_value(tmp_path):
    state = tmp_path / "theses"
    tid = _closed(state)
    # A stored value the YAML writer would alter (hand-edited file with an escaped NEL).
    path = state / f"{tid}.yaml"
    raw = path.read_text(encoding="utf-8")
    assert "lessons_learned: null" in raw
    path.write_text(
        raw.replace("lessons_learned: null", 'lessons_learned: "old\\x85note c"'), encoding="utf-8"
    )
    assert _lessons(state, tid) == "old\x85note c"
    before = _snapshot(state)
    rc, _, err = _record(state, tid, "--text", "clean new text", "--append")
    _assert_clean_error(rc, err, contains="stored")
    assert "--replace" in err
    assert _snapshot(state) == before
    rc, _, err = _record(state, tid, "--text", "clean new text", "--replace")
    assert rc == 0, err
    assert _lessons(state, tid) == "clean new text"


def test_library_non_str_text_raises_value_error(tmp_path):
    state = tmp_path / "theses"
    tid = _closed(state)
    for bad in (123, None, b"bytes"):
        with pytest.raises(ValueError):
            store.record_lessons(state, tid, bad)


def test_cli_works_under_ascii_locale(tmp_path):
    """Explicit encoding='utf-8' reads must not depend on the locale (Windows CI)."""
    state = tmp_path / "theses"
    text = "決算ギャップで買い急いだ"
    ticker = "NIKK"  # ticker and thesis_id are ASCII-only by schema
    tid = _closed(state, ticker)
    assert _record(state, tid, "--text", text)[0] == 0
    env = os.environ.copy()
    env.update({"PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0", "LC_ALL": "C", "LANG": "C"})
    env["PYTHONIOENCODING"] = "utf-8"

    def run(script, *args):
        return subprocess.run(
            [sys.executable, str(script), "--state-dir", str(state), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=60,
        )

    helper = tmp_path / "register_again.py"
    helper.write_text(
        "import json, sys\n"
        f"sys.path.insert(0, {str(STORE_PY.parent)!r})\n"
        "from pathlib import Path\n"
        "import thesis_store\n"
        "print(thesis_store.register(Path(sys.argv[1]), json.loads(sys.argv[2])))\n",
        encoding="utf-8",
    )
    payload = json.dumps(_data(ticker))  # ASCII-escaped, safe as argv under the C locale

    def register_again():
        return subprocess.run(
            [sys.executable, str(helper), str(state), payload],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=60,
        )

    # Same input must dedupe via the index (all indexed fields are ASCII by schema).
    proc = register_again()
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == tid
    # _find_by_fingerprint YAML scan: without the index it must still find the thesis.
    (state / "_index.json").unlink()
    proc = register_again()
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == tid
    assert len(list(state.glob("th_*.yaml"))) == 1

    journal = tmp_path / "j"
    # rebuild_index reads every YAML file; check right away because later commands
    # (postmortem -> update) would re-add the entry to the index on their own.
    proc = run(STORE_PY, "rebuild-index")
    assert proc.returncode == 0, proc.stderr
    index = json.loads((state / "_index.json").read_text(encoding="utf-8"))
    assert index["theses"][tid]["ticker"] == ticker
    for proc in (
        run(STORE_PY, "get", tid),
        run(REVIEW_PY, "postmortem", tid, "--journal-dir", str(journal)),
    ):
        assert proc.returncode == 0, proc.stderr
    doctor = run(STORE_PY, "doctor")
    assert doctor.returncode == 0, doctor.stderr
    assert json.loads(doctor.stdout)["ok"] is True
    assert text in (journal / f"pm_{tid}.md").read_text(encoding="utf-8")
    got = run(STORE_PY, "get", tid)
    assert yaml.safe_load(got.stdout)["outcome"]["lessons_learned"] == text
