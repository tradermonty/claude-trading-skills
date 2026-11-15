"""Saved-input normalization never asserts live completeness or repairs state."""

import copy
import json
import os
import socket
import subprocess
import sys
from decimal import localcontext
from pathlib import Path

import normalize_alpaca_positions as adapter
import pytest
from reconcile_positions import SnapshotError, reconcile

STAMP = "2026-10-20T12:00:00Z"
SCRIPTS = Path(__file__).resolve().parents[1]


def position(symbol="FICTA", qty="2.5", side="long", **extra):
    return dict(symbol=symbol, qty=qty, side=side, asset_class="us_equity", **extra)


def normalize(rows, **kw):
    return adapter.normalize(
        rows,
        kw.pop("account_scope", "paper_demo"),
        kw.pop("as_of", STAMP),
        complete=kw.pop("complete", True),
        **kw,
    )


def test_whitelisted_output_and_native_fixture():
    source = SCRIPTS.parent / "assets/fictional_alpaca_positions.json"
    payload = json.loads(source.read_text())
    payload[0].update(account_id="PRIVATE_ACCOUNT", asset_id="PRIVATE_ASSET", name="PRIVATE_NAME")
    original = copy.deepcopy(payload)
    out = normalize(payload, as_of="2026-10-20T05:00:00-07:00")
    assert set(out) == {"schema_version", "account_scope", "as_of", "complete", "positions"}
    assert out["as_of"] == "2026-10-20T12:00:00+00:00"
    assert out["positions"] == [
        {"symbol": "FICTA", "asset_type": "equity", "direction": "LONG", "quantity": "2.5"},
        {"symbol": "FICTB", "asset_type": "equity", "direction": "SHORT", "quantity": "1"},
    ]
    assert "PRIVATE" not in json.dumps(out)
    assert payload == original


def test_prices_are_not_required_and_symbols_sorted():
    out = normalize([position(" zzz ", "1"), position("aaa", "-0.1250", "short")])
    assert [p["symbol"] for p in out["positions"]] == ["AAA", "ZZZ"]
    assert out["positions"][0]["quantity"] == "0.125"
    assert out["complete"] is True


def test_precision_survives_small_decimal_context():
    qty = "0.123456789012345678901234567890123456789"
    with localcontext() as ctx:
        ctx.prec = 6
        out = normalize([position(qty="-" + qty, side="short")])
    assert out["positions"][0]["quantity"] == qty


@pytest.mark.parametrize("qty", ["0.000000000001", "1000000000000"])
def test_quantity_boundaries(qty):
    assert normalize([position(qty=qty)])["positions"][0]["quantity"] == qty


@pytest.mark.parametrize("complete", [False, None, 1, "true"])
def test_empty_requires_explicit_true(complete):
    with pytest.raises(SnapshotError):
        normalize([], complete=complete)
    with pytest.raises(SnapshotError):
        adapter.normalize([], "paper_demo", STAMP)


def test_explicit_empty_is_valid():
    out = normalize([])
    assert out["positions"] == []
    assert reconcile(out, out)["can_continue"] is True


@pytest.mark.parametrize("payload", [None, {}, {"error": "PRIVATE"}, {"positions": []}, "[]"])
def test_non_lists_are_not_empty_accounts(payload):
    with pytest.raises(SnapshotError) as exc:
        normalize(payload)
    assert "PRIVATE" not in str(exc.value)


@pytest.mark.parametrize(
    "patch",
    [
        {"symbol": None},
        {"symbol": "PRIVATE|ACCOUNT"},
        {"symbol": ""},
        {"asset_class": "crypto"},
        {"asset_class": "us_option"},
        {"asset_class": None},
        {"currency": "EUR"},
        {"currency": None},
        {"side": "LONG"},
        {"side": "sell"},
        {"side": None},
        {"qty": "-1"},
        {"qty": "0"},
        {"qty": "-0"},
        {"qty": "NaN"},
        {"qty": "Infinity"},
        {"qty": "1e-3"},
        {"qty": " 1"},
        {"qty": "1 "},
        {"qty": "+1"},
        {"qty": True},
        {"qty": 1.25},
        {"qty": None},
        {"qty": "1" * 65},
        {"qty": "0.0000000000001"},
        {"qty": "1000000000001"},
        {"qty": "1", "side": "short"},
    ],
)
def test_invalid_native_row_blocks_entire_export(patch):
    bad = position(**{"account_id": "PRIVATE_ACCOUNT"})
    bad.update(patch)
    with pytest.raises(SnapshotError) as exc:
        normalize([position("GOOD"), bad])
    assert "PRIVATE" not in str(exc.value)


@pytest.mark.parametrize("row", [None, [], "PRIVATE"])
def test_invalid_row_shapes(row):
    with pytest.raises(SnapshotError) as exc:
        normalize([row])
    assert "PRIVATE" not in str(exc.value)


def test_duplicate_identity_is_not_summed():
    with pytest.raises(SnapshotError, match="duplicate"):
        normalize([position(" aaa "), position("AAA", "-1", "short")])


@pytest.mark.parametrize(
    "kw",
    [
        {"account_scope": "PRIVATE|ACCOUNT"},
        {"account_scope": ""},
        {"as_of": "2026-10-20"},
        {"as_of": "PRIVATE"},
    ],
)
def test_assertions_use_existing_contract(kw):
    with pytest.raises(SnapshotError) as exc:
        normalize([], **kw)
    assert "PRIVATE" not in str(exc.value)


def args(source, *extra):
    return [
        "--positions-json",
        str(source),
        "--account-scope",
        "paper_demo",
        "--as-of",
        STAMP,
        "--confirm-complete",
        *map(str, extra),
    ]


def test_cli_stdout_is_offline_and_source_unchanged(tmp_path, capsys, monkeypatch):
    source = tmp_path / "PRIVATE_SOURCE.json"
    source.write_text(json.dumps([position(account_id="PRIVATE_ACCOUNT")]))
    before = source.read_bytes(), source.stat().st_mtime_ns
    monkeypatch.setattr(socket.socket, "connect", lambda *a: pytest.fail("network forbidden"))
    assert adapter.main(args(source)) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["positions"][0]["asset_type"] == "equity"
    assert "PRIVATE" not in captured.out + captured.err
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before


def test_new_file_output_is_complete_and_private(tmp_path, capsys):
    source, out = tmp_path / "source.json", tmp_path / "out.json"
    source.write_text(json.dumps([position()]))
    assert adapter.main(args(source, "--output", out)) == 0
    assert json.loads(out.read_text()) == normalize([position()])
    assert "positions" not in capsys.readouterr().out
    if os.name == "posix":
        assert out.stat().st_mode & 0o777 == 0o600
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.json", "source.json"]


@pytest.mark.parametrize("kind", ["existing", "input", "hardlink", "symlink"])
def test_outputs_never_clobber_input_or_existing_data(tmp_path, capsys, kind):
    source, out = tmp_path / "source.json", tmp_path / "out.json"
    source.write_text(json.dumps([position()]))
    if kind == "input":
        out = source
    elif kind == "hardlink":
        os.link(source, out)
    elif kind == "symlink":
        try:
            out.symlink_to(source)
        except OSError:
            pytest.skip("symlink creation unavailable")
    else:
        out.write_text("PRIVATE_KEEP")
    before = source.read_bytes(), out.read_bytes()
    assert adapter.main(args(source, "--output", out)) == 1
    assert (source.read_bytes(), out.read_bytes()) == before
    captured = capsys.readouterr()
    assert captured.out == "" and "PRIVATE" not in captured.err
    assert not list(tmp_path.glob(".alpaca-reconciliation-*"))


def test_failed_atomic_publication_cleans_up(tmp_path, monkeypatch, capsys):
    source, out = tmp_path / "source.json", tmp_path / "out.json"
    source.write_text("[]")

    def fail(*args, **kw):
        raise OSError("PRIVATE_ERROR")

    monkeypatch.setattr(adapter.os, "link", fail)
    assert adapter.main(args(source, "--output", out)) == 1
    assert list(tmp_path.iterdir()) == [source]
    assert "PRIVATE" not in capsys.readouterr().err


def test_staging_write_failure_never_publishes(tmp_path, monkeypatch, capsys):
    source, out = tmp_path / "source.json", tmp_path / "out.json"
    source.write_text("[]")

    def fail(*args):
        raise OSError("PRIVATE_WRITE_ERROR")

    monkeypatch.setattr(adapter.os, "fsync", fail)
    assert adapter.main(args(source, "--output", out)) == 1
    assert list(tmp_path.iterdir()) == [source]
    captured = capsys.readouterr()
    assert captured.out == "" and "PRIVATE" not in captured.err


@pytest.mark.parametrize("flag", ["--confirm-complete", "--as-of", "--account-scope"])
def test_cli_assertions_are_required(tmp_path, flag):
    source = tmp_path / "source.json"
    source.write_text("[]")
    argv = args(source)
    index = argv.index(flag)
    del argv[index : index + (1 if flag == "--confirm-complete" else 2)]
    with pytest.raises(SystemExit) as exc:
        adapter.main(argv)
    assert exc.value.code == 2


@pytest.mark.parametrize("kind", ["missing", "encoding", "directory"])
def test_read_errors_hide_paths_and_data(tmp_path, capsys, kind):
    source = tmp_path / "PRIVATE_SOURCE"
    if kind == "encoding":
        source.write_bytes(b"\xffPRIVATE")
    elif kind == "directory":
        source.mkdir()
    assert adapter.main(args(source)) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "PRIVATE" not in captured.err and "Traceback" not in captured.err


@pytest.mark.parametrize(
    "text", ['{"PRIVATE":1,"PRIVATE":2}', '[{"symbol":"PRIVATE"}', "[" * 3000 + "]" * 3000]
)
def test_safe_read_failure_has_no_export(tmp_path, capsys, text):
    source, out = tmp_path / "PRIVATE_SOURCE.json", tmp_path / "out.json"
    source.write_text(text)
    assert adapter.main(args(source, "--output", out)) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "PRIVATE" not in captured.err and "Traceback" not in captured.err
    assert not out.exists()


@pytest.mark.parametrize(
    "qty,direction,expected,exit_code,memory_empty",
    [
        ("2.5", "long", "MATCH", 0, False),
        ("2.0", "long", "QUANTITY_MISMATCH", 1, False),
        ("-2.5", "short", "DIRECTION_MISMATCH", 1, False),
        ("2.5", "long", "BROKER_ONLY", 1, True),
        (None, "long", "MEMORY_ONLY", 1, False),
    ],
)
def test_actual_normalizer_then_reconciler_clis(
    tmp_path, qty, direction, expected, exit_code, memory_empty
):
    source, broker, memory = [tmp_path / n for n in ("native.json", "broker.json", "memory.json")]
    source.write_text(json.dumps([position(qty=qty, side=direction)] if qty is not None else []))
    memory.write_text(json.dumps(normalize([] if memory_empty else [position()])))
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "normalize_alpaca_positions.py"),
            *args(source, "--output", broker),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "reconcile_positions.py"),
            "--broker",
            str(broker),
            "--memory",
            str(memory),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=30,
    )
    assert result.returncode == exit_code, result.stderr
    report = json.loads(result.stdout)
    assert report["items"][0]["status"] == expected
    assert report["can_continue"] is (exit_code == 0)
