"""Uncoercible CSV numbers must not abort the complete provider canary.

Run the actual parser, HTTP wrapper and CLI in a child with a known integer
conversion limit. The parent interpreter's process-wide policy stays untouched.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

PROBE = r"""
import contextlib
import csv
import io
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from scripts import check_provider_contracts as checker
from scripts.provider_contracts import load_contracts, parse_csv_rows

mode, cell = sys.argv[2:4]
assert sys.get_int_max_str_digits() == 640
body = ('count\n12\n' + cell + '\n').encode()
if mode == 'parse':
    try:
        rows, anomalies = parse_csv_rows(body.decode())
    except csv.Error as exc:
        print(json.dumps({'error': str(exc), 'traceback': traceback.format_exc()}))
    else:
        print(json.dumps({'rows': rows, 'anomalies': [a.code for a in anomalies]}))
    sys.exit(0)

import requests
class Response:
    status_code = 200
    def __init__(self, body):
        self.body = body
        self.closed = False
    def iter_content(self, chunk_size):
        for start in range(0, len(self.body), chunk_size):
            yield self.body[start:start + chunk_size]
    def close(self):
        self.closed = True

responses = []
calls = []
contracts = {name: c for name, c in load_contracts(sys.argv[1]).items()
             if c.provider == 'trader-monty'}
bad = sorted(contracts)[0]

def fixture_csv(rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    text = io.StringIO()
    writer = csv.DictWriter(text, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return text.getvalue().encode()

bodies = {c.url: fixture_csv(c.fixture) for c in contracts.values()}
bodies[contracts[bad].url] = body

def fake_get(url, **kwargs):
    assert kwargs == {'timeout': 30, 'stream': True, 'allow_redirects': False}
    calls.append(url)
    response = Response(bodies[url])
    responses.append(response)
    return response

requests.get = fake_get
if mode == 'fetch':
    result = checker._build_public_csv_fetch()(contracts[bad])
    print(json.dumps({'status': result.status, 'rows': result.rows,
                      'anomalies': [[a.code, a.severity] for a in result.extra_anomalies],
                      'closed': all(r.closed for r in responses)}))
elif mode == 'canary':
    report_path = Path(sys.argv[4])
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = checker.main(['canary', '--provider', 'trader-monty',
                             '--report', str(report_path)])
    print(json.dumps({'code': code, 'report': json.loads(report_path.read_text()),
                      'bad': bad, 'called': calls, 'expected': [c.url for c in contracts.values()],
                      'closed': all(r.closed for r in responses),
                      'stdout': stdout.getvalue(), 'stderr': stderr.getvalue()}))
else:
    raise AssertionError('unexpected probe mode')
"""


def probe(mode, cell, tmp_path):
    if not hasattr(sys, "get_int_max_str_digits"):
        pytest.skip("this interpreter has no integer digit safety limit")
    original_limit = sys.get_int_max_str_digits()
    env = {**os.environ, "PYTHONINTMAXSTRDIGITS": "640"}
    result = subprocess.run(
        [sys.executable, "-c", PROBE, str(ROOT), mode, cell, str(tmp_path / "canary.json")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert sys.get_int_max_str_digits() == original_limit
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    return json.loads(result.stdout)


@pytest.mark.parametrize("digits", [639, 640])
@pytest.mark.parametrize("sign", ["", "+", "-"])
def test_integer_boundary_remains_valid(digits, sign, tmp_path):
    cell = sign + "7" * digits
    result = probe("parse", cell, tmp_path)
    assert result == {"rows": [{"count": 12}, {"count": int(cell)}], "anomalies": []}


@pytest.mark.parametrize("sign", ["", "+", "-"])
@pytest.mark.parametrize("digits", [641, 5000])
def test_integer_over_limit_is_safe_csv_error(sign, digits, tmp_path):
    cell = sign + "7" * digits
    result = probe("parse", cell, tmp_path)
    assert result["error"] == "Integer cell exceeds supported conversion limits"
    assert "rows" not in result
    assert cell not in result["traceback"]
    assert "ValueError" not in result["traceback"]
    assert "csv.Error" in result["traceback"] or "_csv.Error" in result["traceback"]


def test_uncoercible_http_csv_discards_prefix_and_closes_response(tmp_path):
    cell = "7" * 5000
    result = probe("fetch", cell, tmp_path)
    assert result == {
        "status": 200,
        "rows": None,
        "anomalies": [["parse_error", "fatal"]],
        "closed": True,
    }
    assert cell not in json.dumps(result)


def test_uncoercible_csv_writes_complete_report_and_continues_later_probes(tmp_path):
    cell = "7" * 5000
    result = probe("canary", cell, tmp_path)
    assert result["code"] == 1
    assert result["closed"]
    assert sorted(result["called"]) == sorted(result["expected"])
    assert len(result["called"]) == len(set(result["called"])) == 4
    report = result["report"]
    assert report["ok"] is False
    assert report["budget"] == {"max": 4, "used": 4}
    assert len(report["contracts"]) == 4
    bad = report["contracts"][result["bad"]]
    assert bad == {
        "status": 200,
        "rows": 0,
        "ok": False,
        "anomalies": [{"code": "parse_error", "severity": "fatal", "count": 1}],
        "deprecations": [],
    }
    assert all(entry["ok"] for name, entry in report["contracts"].items() if name != result["bad"])
    assert cell not in json.dumps(result)
    assert "ValueError" not in result["stdout"] + result["stderr"]
