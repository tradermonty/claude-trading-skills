"""Run the exact library examples without provider I/O or demo defaults."""

import json
import math
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PAGES = [
    "CLAUDE.md",
    "docs/en/skills/options-strategy-advisor.md",
    "docs/ja/skills/options-strategy-advisor.md",
    "skills/options-strategy-advisor/SKILL.md",
]


def _example(page):
    text = (ROOT / page).read_text()
    assert "black_scholes CLI is a research entry point" not in text
    assert "--iv" not in text, f"{page} documents a flag black_scholes.py does not parse"
    assert not re.search(
        r"python3?\s+(?:skills/options-strategy-advisor/)?scripts/black_scholes\.py", text
    )
    blocks = re.findall(r"<!-- options-library-example -->\s*```python\n(.*?)\n```", text, re.S)
    assert len(blocks) == 1
    return blocks[0]


@pytest.mark.parametrize("page", PAGES)
def test_exact_example_uses_real_inputs_offline(page):
    code = _example(page)
    outputs = []
    for stock_price in (100.0, 110.0):
        example = code.replace("S=100.0", f"S={stock_price}")
        program = (
            """
import socket
socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(AssertionError('unexpected network'))
socket.getaddrinfo = lambda *a, **k: (_ for _ in ()).throw(AssertionError('unexpected DNS'))
"""
            + example
            + "\nimport json\nprint('RESULT:' + json.dumps({k: float(v) for k,v in greeks.items()}))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", program],
            cwd=ROOT / "skills/options-strategy-advisor" if page.startswith("skills/") else ROOT,
            env={**os.environ, "FMP_API_KEY": "", "FINVIZ_API_KEY": ""},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout.split("RESULT:")[-1])
        assert set(data) == {
            "price",
            "delta",
            "gamma",
            "theta",
            "vega",
            "rho",
            "intrinsic_value",
            "time_value",
        }
        assert all(math.isfinite(value) for value in data.values())
        outputs.append(data)
    # Independent closed-form ATM zero-rate, zero-dividend one-year reference.
    assert outputs[0]["price"] == pytest.approx(7.965567455, abs=1e-8)
    assert outputs[0]["delta"] == pytest.approx(0.539827837, abs=1e-8)
    assert outputs[1]["price"] > outputs[0]["price"]
    assert outputs[1]["delta"] > outputs[0]["delta"]


def test_language_examples_match():
    assert (
        len(
            {
                _example(page).replace("skills/options-strategy-advisor/scripts", "scripts")
                for page in PAGES
            }
        )
        == 1
    )


def test_packaged_skill_matches_source():
    with zipfile.ZipFile(ROOT / "skill-packages/options-strategy-advisor.skill") as archive:
        assert (
            archive.read("options-strategy-advisor/SKILL.md").decode()
            == (ROOT / PAGES[-1]).read_text()
        )
