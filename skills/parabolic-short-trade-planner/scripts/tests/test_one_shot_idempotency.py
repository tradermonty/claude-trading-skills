"""Idempotency contract test: running the Phase 3 pipeline N times
against the same fixture + same --now-et must produce byte-identical
output (after normalising the wall-clock-stamped fields).

This test is the safety net for the v0.5c contract that prior_state
is read by the CLI for diff/notification only and never feeds the
FSM. If a future refactor accidentally lets prior_state advance the
FSM, this test will fail because the second run would diverge from
the first.
"""

from __future__ import annotations

import re
from pathlib import Path

import monitor_intraday_trigger as mit

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Fields that legitimately vary between runs (wall clock); we strip
# them before byte-comparing.
WALL_CLOCK_FIELDS = re.compile(r'"(?:evaluated_at|last_evaluated_at|written_at)": "[^"]*"')


def _normalise(text: str) -> str:
    return WALL_CLOCK_FIELDS.sub('"_": "X"', text)


def _run(tmp_root: Path, label: str) -> str:
    out_dir = tmp_root / f"out_{label}"
    state_dir = tmp_root / f"state_{label}"
    rc = mit.main(
        [
            "--plans-json",
            str(FIXTURES / "phase2_plan_smoke.json"),
            "--bars-source",
            "fixture",
            "--bars-fixture",
            str(FIXTURES / "intraday_bars" / "orl_clean_break.json"),
            "--state-dir",
            str(state_dir),
            "--output-dir",
            str(out_dir),
            "--as-of",
            "2026-05-05",
            "--now-et",
            "2026-05-05T10:00:00-04:00",
        ]
    )
    assert rc == 0
    out_files = list(out_dir.glob("*.json"))
    assert len(out_files) == 1
    return _normalise(out_files[0].read_text())


class TestIdempotency:
    def test_three_runs_byte_identical(self, tmp_path):
        out1 = _run(tmp_path, "run1")
        out2 = _run(tmp_path, "run2")
        out3 = _run(tmp_path, "run3")
        assert out1 == out2 == out3, (
            "Phase 3 outputs diverged between runs. The FSM may be "
            "reading prior_state, which violates the v0.5 idempotency "
            "contract."
        )

    def test_state_persistence_does_not_change_output(self, tmp_path):
        """Run #1 with empty state dir; Run #2 reuses the same state
        dir (so prior_state files exist). Output must be identical."""
        # Run 1 — empty state dir.
        out_dir = tmp_path / "out"
        state_dir = tmp_path / "state"
        for label in ("run1", "run2"):
            mit.main(
                [
                    "--plans-json",
                    str(FIXTURES / "phase2_plan_smoke.json"),
                    "--bars-source",
                    "fixture",
                    "--bars-fixture",
                    str(FIXTURES / "intraday_bars" / "orl_clean_break.json"),
                    "--state-dir",
                    str(state_dir),
                    "--output-dir",
                    str(out_dir / label),
                    "--as-of",
                    "2026-05-05",
                    "--now-et",
                    "2026-05-05T10:00:00-04:00",
                ]
            )
        run1 = _normalise(
            (out_dir / "run1" / "parabolic_short_intraday_2026-05-05.json").read_text()
        )
        run2 = _normalise(
            (out_dir / "run2" / "parabolic_short_intraday_2026-05-05.json").read_text()
        )
        assert run1 == run2, (
            "Output diverged between two runs sharing the same state dir. "
            "The FSM is reading prior_state — this violates the idempotency "
            "contract."
        )
