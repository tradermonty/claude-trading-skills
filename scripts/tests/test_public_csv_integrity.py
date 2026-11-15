"""HTTP 200 must not conceal ambiguous CSV structure in #332's canary."""

import csv
import io
import json
from pathlib import Path

import pytest

from scripts import check_provider_contracts as cli
from scripts.provider_contracts import FATAL, load_contracts, parse_csv_rows, validate_rows

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = {k: v for k, v in load_contracts(ROOT).items() if v.format == "csv"}


@pytest.mark.parametrize(
    "text,code",
    [
        ("value,value\n999,1\n", "duplicate_header"),
        ('"value","value"\n999,1\n', "duplicate_header"),
        ('"a,b","a,b"\n999,1\n', "duplicate_header"),
        ("value,value\n", "duplicate_header"),
        ("PRIVATE_HEADER,PRIVATE_HEADER\n1,2\n", "duplicate_header"),
        ("value,\n1,2\n", "blank_header"),
        ("value, \t\n1,2\n", "blank_header"),
        (",value\n1,2\n", "blank_header"),
        ('"",value\n1,2\n', "blank_header"),
    ],
)
def test_invalid_header_never_produces_collapsed_rows(text, code):
    rows, anomalies = parse_csv_rows(text)
    assert rows == []
    assert [(a.code, a.severity) for a in anomalies] == [(code, FATAL)]


@pytest.mark.parametrize(
    "text",
    [
        'value\n"1\n',
        'value\n1\n"2\n',  # valid prefix must never survive a later parse error
        'value\n"1"garbage\n',
        '"value\n1\n',
        "value\n1\x00\n",
        "value\x00,value\n1,2\n",
        "\x00extra_cells\n1\n",  # reserved DictReader overflow key
    ],
)
def test_malformed_csv_raises_without_partial_results(text):
    with pytest.raises(csv.Error):
        parse_csv_rows(text)


@pytest.mark.parametrize(
    "text,expected",
    [
        ('\ufeffname,value\r\n"ACME, Inc",1\r\n', [{"name": "ACME, Inc", "value": 1}]),
        ('name,value\n"line1\nline2",1\n', [{"name": "line1\nline2", "value": 1}]),
        ('name,value\n"ACME ""Inc""",1\n', [{"name": 'ACME "Inc"', "value": 1}]),
        ("Value,value\n1,2\n", [{"Value": 1, "value": 2}]),
        ("name, value\nA,2\n", [{"name": "A", " value": 2}]),
        ("a,b\n", []),
        ("", []),
        ("\ufeff", []),
    ],
)
def test_valid_csv_and_exact_field_identity_remain_supported(text, expected):
    assert parse_csv_rows(text) == (expected, [])


def fixture_csv(contract):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(contract.fixture[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(contract.fixture)
    return out.getvalue()


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_recorded_csv_fixtures_still_satisfy_contracts(name):
    contract = CONTRACTS[name]
    rows, anomalies = parse_csv_rows(fixture_csv(contract))
    assert anomalies == []
    assert validate_rows(contract, rows).ok


class Response:
    status_code = 200

    def __init__(self, body):
        self.body = body.encode("utf-8")
        self.closed = False

    def iter_content(self, chunk_size):
        for start in range(0, len(self.body), 7):
            yield self.body[start : start + 7]

    def close(self):
        self.closed = True


@pytest.mark.parametrize(
    "corruption,code",
    [
        ("duplicate", "duplicate_header"),
        ("blank", "blank_header"),
        ("unclosed", "parse_error"),
        ("late_unclosed", "parse_error"),
        ("unclosed_last_value", "parse_error"),
        ("nul", "parse_error"),
    ],
)
@pytest.mark.parametrize("bad_name", sorted(CONTRACTS))
def test_corrupt_http200_is_reported_and_other_contracts_continue(
    monkeypatch, tmp_path, capsys, corruption, code, bad_name
):
    import requests

    marker = "PRIVATE_HEADER_AND_CELL"
    bad = CONTRACTS[bad_name]
    body = fixture_csv(bad)
    lines = body.splitlines()
    if corruption == "duplicate":
        # Duplicate an actual required field: DictReader used to silently overwrite it.
        field = next(iter(bad.required_fields))
        records = list(csv.reader(io.StringIO(body)))
        column = records[0].index(field)
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow([*records[0], field])
        writer.writerows([*row, row[column]] for row in records[1:])
        body = out.getvalue()
    elif corruption == "blank":
        lines[0] += ", "
        lines[1:] = [line + "," + marker for line in lines[1:]]
        body = "\n".join(lines) + "\n"
    elif corruption == "unclosed":
        body = lines[0] + '\n"' + marker
    elif corruption == "late_unclosed":
        body += '"' + marker
    elif corruption == "unclosed_last_value":
        # All required fields remain valid-looking with the old permissive parser.
        records = list(csv.reader(io.StringIO(body)))
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerows(records[:-1])
        writer.writerow(records[-1][:-1])
        body = out.getvalue().rstrip("\n") + ',"' + records[-1][-1].replace('"', '""')
    else:
        body += "\x00" + marker

    bodies = {
        c.url: (body if name == bad_name else fixture_csv(c)) for name, c in CONTRACTS.items()
    }
    responses = []
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        assert kwargs == {"timeout": 30, "allow_redirects": False, "stream": True}
        response = Response(bodies[url])
        responses.append(response)
        return response

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    report_file = tmp_path / "report.json"
    result = cli.main(["canary", "--provider", "trader-monty", "--report", str(report_file)])
    assert result == 1
    report = json.loads(report_file.read_text())
    assert set(report["contracts"]) == set(CONTRACTS)
    assert report["ok"] is False
    broken = report["contracts"][bad_name]
    assert broken["status"] == 200 and broken["ok"] is False and broken["rows"] == 0
    assert {a["code"] for a in broken["anomalies"]} >= {code}
    assert all(a["severity"] == "fatal" for a in broken["anomalies"])
    assert all(v["ok"] for name, v in report["contracts"].items() if name != bad_name)
    assert report["budget"] == {"max": len(CONTRACTS), "used": len(CONTRACTS)}
    assert len(calls) == len(set(calls)) == len(CONTRACTS)
    assert all(r.closed for r in responses)
    summary = cli.render_summary(report)
    assert code in summary
    captured = capsys.readouterr()
    assert marker not in report_file.read_text() + summary + captured.out + captured.err
