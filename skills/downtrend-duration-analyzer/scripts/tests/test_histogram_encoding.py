"""Dynamic report values remain data in HTML and JavaScript contexts."""

import json
import shutil
import subprocess
import sys
from html.parser import HTMLParser

import generate_histogram_html as ghh
import pytest
from generate_histogram_html import generate_html, generate_sector_options


class ReportParser(HTMLParser):
    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.text = []
        self.scripts = []
        self.in_script = False
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == "script":
            self.in_script = True
            self.scripts.append("")

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.in_script:
            self.scripts[-1] += data
        else:
            self.text.append(data)


@pytest.mark.parametrize(
    "value",
    [
        "</ScRiPt><script>globalThis.reportMarker=1</script>",
        "<!--<script></script>",
        "Energy & Metals \"quoted\" <growth> 'value' 日本語\u2028\u2029",
    ],
)
def test_embedded_data_cannot_change_script_boundaries(value):
    data = [{"symbol": value, "sector": "Energy", "duration_days": 5}]
    parsed = ReportParser(generate_html({"downtrends": data}))
    assert [tag for tag, _ in parsed.tags].count("script") == 2
    script = parsed.scripts[1]
    embedded = script.split("const allDowntrends = ", 1)[1].split(";\n", 1)[0]
    assert "<" not in embedded
    assert json.loads(embedded) == data
    assert "updateCharts();" in script


def test_sector_option_preserves_value_and_label_without_creating_attributes():
    sector = '"><img src=x onerror="reportMarker=1"> & <Energy> \'growth\''
    parsed = ReportParser(generate_sector_options([{"sector": sector}]))
    assert parsed.tags == [("option", {"value": sector})]
    assert parsed.text[-1] == sector


@pytest.mark.parametrize(
    "field", ["analysis_date", "lookback_years", "peak_window", "min_depth_pct"]
)
def test_report_metadata_is_text(field):
    value = '<b>unsafe</b> & "quoted"'
    data = {"parameters": {}}
    if field == "analysis_date":
        data[field] = value
        expected = value[:10]
    else:
        data["parameters"][field] = value
        expected = value
    parsed = ReportParser(generate_html(data))
    assert "b" not in [tag for tag, _ in parsed.tags]
    assert expected in "".join(parsed.text)


def test_total_count_keeps_thousands_separator():
    parsed = ReportParser(generate_html({"summary": {"total_downtrends": 12345}}))
    assert "Total Downtrends: 12,345" in "".join(parsed.text)


def test_runtime_stats_use_text_and_filters_keep_original_sector_values():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed for the JavaScript runtime regression")
    sector = 'Energy & Metals "<growth>"'
    value = '<img src=x onerror="globalThis.reportMarker=1">'
    rows = [
        {"sector": sector, "market_cap_tier": "Large", "duration_days": value},
        {"sector": "Other", "market_cap_tier": "Small", "duration_days": 12},
    ]
    script = ReportParser(generate_html({"downtrends": rows})).scripts[1]
    harness = r"""
const vm = require('node:vm');
const assert = require('node:assert/strict');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const grid = {children: [], replaceChildren(...children) { this.children = children; }};
const nodes = {
  sectorFilter: {value: input.sector}, marketCapFilter: {value: 'all'},
  binSize: {value: '10'}, statsGrid: grid
};
const document = {
  getElementById(id) { return nodes[id]; },
  createElement() {
    return {children: [], append(...children) { this.children.push(...children); },
      set innerHTML(value) { throw Error('HTML parsing sink used'); }};
  }
};
const context = vm.createContext({document, Plotly: {newPlot() {}}});
vm.runInContext(input.script, context);
assert.equal(vm.runInContext('filterData().length', context), 1);
assert.equal(grid.children.length, 6);
assert.equal(grid.children[3].children[0].textContent, input.value);
assert.equal(context.reportMarker, undefined);
nodes.sectorFilter.value = 'all';
nodes.marketCapFilter.value = 'Small';
vm.runInContext('updateCharts()', context);
assert.equal(grid.children[3].children[0].textContent, '12');
nodes.marketCapFilter.value = 'Mega';
vm.runInContext('updateCharts()', context);
assert.equal(grid.children.length, 1);
assert.equal(grid.children[0].children[1].textContent, 'No Data');
"""
    subprocess.run(
        [node, "-e", harness],
        input=json.dumps({"script": script, "sector": sector, "value": value}),
        text=True,
        check=True,
        capture_output=True,
        timeout=15,
    )


def test_cli_writes_encoded_report(tmp_path, monkeypatch):
    value = "</script><script>globalThis.reportMarker=1</script>"
    rows = [{"symbol": value, "sector": value, "duration_days": 5}]
    source = tmp_path / "analysis.json"
    source.write_text(json.dumps({"downtrends": rows}), encoding="utf-8")
    output = tmp_path / "reports"
    monkeypatch.setattr(
        sys, "argv", ["report", "--input", str(source), "--output-dir", str(output)]
    )
    ghh.main()
    parsed = ReportParser(next(output.glob("*.html")).read_text(encoding="utf-8"))
    assert [tag for tag, _ in parsed.tags].count("script") == 2
    assert any(attrs.get("value") == value for tag, attrs in parsed.tags if tag == "option")
    embedded = parsed.scripts[1].split("const allDowntrends = ", 1)[1].split(";\n", 1)[0]
    assert json.loads(embedded) == rows
