"""Regression tests for the committed skill-guide drift ceiling (#665)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import report_skill_doc_drift as drift


class DriftCeilingTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        skill = self.root / "skills/demo"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("Use --alpha and --beta.\n", encoding="utf-8")
        page = self.root / "docs/en/skills/demo.md"
        page.parent.mkdir(parents=True)
        page.write_text("# Guide\n--alpha\n", encoding="utf-8")
        self.output = self.root / "report.md"

    def tearDown(self):
        self.temporary.cleanup()

    def _write_ceiling(self, pages):
        path = self.root / "docs/dev/skill-doc-drift-baseline.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"schema_version": 1, "drift_pages": pages}), encoding="utf-8"
        )
        return path

    def _run(self, *extra):
        return drift.main(
            ["--root", str(self.root), "--markdown-output", str(self.output), *extra]
        )

    def test_default_ceiling_fails_on_new_drift(self):
        self._write_ceiling(0)
        self.assertEqual(self._run(), 1)

    def test_ceiling_that_matches_or_exceeds_drift_passes(self):
        self._write_ceiling(1)
        self.assertEqual(self._run(), 0)

    def test_malformed_ceiling_fails_closed(self):
        path = self._write_ceiling(0)
        path.write_text("{", encoding="utf-8")
        self.assertEqual(self._run(), 1)

    def test_missing_ceiling_keeps_report_only_mode(self):
        self.assertEqual(self._run(), 0)


if __name__ == "__main__":
    unittest.main()
