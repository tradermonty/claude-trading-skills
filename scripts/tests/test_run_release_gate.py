"""Tests for scripts/run_release_gate.py — CI release gate failure modes."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from run_release_gate import (  # noqa: E402
    _grep_oanda,
    _check_forbidden_language,
    _check_audit_log_chain,
    _check_ceremony_log,
    main,
)


# ---------------------------------------------------------------------------
# _grep_oanda — OANDA boundary
# ---------------------------------------------------------------------------

class TestGrepOanda:
    def test_passes_when_no_oanda_imports(self, tmp_path: Path) -> None:
        script = tmp_path / "clean.py"
        script.write_text("import os\nprint('hello')\n")
        assert _grep_oanda(tmp_path) is True

    def test_fails_when_oanda_trader_imported(self, tmp_path: Path) -> None:
        script = tmp_path / "bad.py"
        # Split string to avoid triggering the repo-level boundary scanner
        script.write_text("import " + "oanda_trader\n")
        assert _grep_oanda(tmp_path) is False

    def test_fails_when_from_oanda_trader_imported(self, tmp_path: Path) -> None:
        script = tmp_path / "bad.py"
        # Split string to avoid triggering the repo-level boundary scanner
        # Policy specifically targets the oanda_trader module (not generic oanda_*)
        script.write_text("from " + "oanda_trader import api\n")
        assert _grep_oanda(tmp_path) is False

    def test_skips_test_files(self, tmp_path: Path) -> None:
        # test_ files are skipped (split string to avoid repo boundary scanner)
        test_file = tmp_path / "test_oanda.py"
        test_file.write_text("import " + "oanda_trader  # reference in test\n")
        assert _grep_oanda(tmp_path) is True

    def test_skips_pycache_dirs(self, tmp_path: Path) -> None:
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "bad.py").write_text("import " + "oanda_trader\n")
        assert _grep_oanda(tmp_path) is True


# ---------------------------------------------------------------------------
# _check_forbidden_language — SKILL.md scan
# ---------------------------------------------------------------------------

class TestCheckForbiddenLanguage:
    def test_passes_when_no_skill_mds(self, tmp_path: Path) -> None:
        assert _check_forbidden_language(tmp_path) is True

    def test_passes_with_clean_skill_md(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "# My Skill\nAnalyze the chart and generate a report.\n"
        )
        assert _check_forbidden_language(tmp_path) is True

    def test_fails_when_execute_order_found(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skills" / "bad-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("Execute order at market.\n")
        assert _check_forbidden_language(tmp_path) is False

    def test_fails_when_submit_order_found(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skills" / "bad-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("Submit order via broker.\n")
        assert _check_forbidden_language(tmp_path) is False

    def test_fails_when_auto_trade_found(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skills" / "bad-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("Enable auto-trade mode.\n")
        assert _check_forbidden_language(tmp_path) is False

    def test_case_insensitive(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skills" / "bad-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("EXECUTE ORDER NOW\n")
        assert _check_forbidden_language(tmp_path) is False

    def test_negated_form_allowed(self, tmp_path: Path) -> None:
        """Phrases like 'this skill does not place orders' must NOT be flagged."""
        skill_dir = tmp_path / "skills" / "good-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "This skill does not place orders — it is decision-support only.\n"
            "This skill does not execute orders automatically.\n"
            "Do not use this skill to place orders or submit orders.\n"
        )
        assert _check_forbidden_language(tmp_path) is True

    def test_negated_form_in_same_sentence_allowed(self, tmp_path: Path) -> None:
        """Negation within 120 chars before the phrase in the same clause is respected."""
        skill_dir = tmp_path / "skills" / "good-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "Note: this tool never submits orders or executes trades automatically.\n"
        )
        assert _check_forbidden_language(tmp_path) is True

    def test_new_sentence_after_negation_still_caught(self, tmp_path: Path) -> None:
        """A genuine forbidden phrase in a new sentence after a negation is flagged."""
        skill_dir = tmp_path / "skills" / "bad-skill"
        skill_dir.mkdir(parents=True)
        # The period resets the context — "place order" in the next sentence is genuine.
        (skill_dir / "SKILL.md").write_text(
            "This skill does not review portfolios. Place order immediately at open.\n"
        )
        assert _check_forbidden_language(tmp_path) is False


# ---------------------------------------------------------------------------
# _check_audit_log_chain
# ---------------------------------------------------------------------------

class TestCheckAuditLogChain:
    def test_passes_when_no_log_exists(self, tmp_path: Path) -> None:
        assert _check_audit_log_chain(tmp_path) is True

    def test_passes_with_valid_chain(self, tmp_path: Path) -> None:
        sys.path.insert(0, str(SCRIPTS_DIR))
        from audit_log import AuditLog, AuditEventType
        log = AuditLog(tmp_path / "state" / "audit-log")
        log.append(AuditEventType.WORKFLOW_STARTED, actor="alice")
        log.append(AuditEventType.REVIEW_APPROVED, actor="bob")
        assert _check_audit_log_chain(tmp_path) is True

    def test_fails_with_tampered_log(self, tmp_path: Path) -> None:
        from audit_log import AuditLog, AuditEventType
        log = AuditLog(tmp_path / "state" / "audit-log")
        log.append(AuditEventType.WORKFLOW_STARTED, actor="alice")
        # Tamper
        lines = log.log_file.read_text().splitlines()
        entry = json.loads(lines[0])
        entry["actor"] = "mallory"
        lines[0] = json.dumps(entry)
        log.log_file.write_text("\n".join(lines) + "\n")
        assert _check_audit_log_chain(tmp_path) is False


# ---------------------------------------------------------------------------
# _check_ceremony_log
# ---------------------------------------------------------------------------

class TestCheckCeremonyLog:
    def test_passes_in_non_strict_when_no_log(self, tmp_path: Path) -> None:
        assert _check_ceremony_log(tmp_path, strict=False) is True

    def test_fails_in_strict_when_no_log(self, tmp_path: Path) -> None:
        assert _check_ceremony_log(tmp_path, strict=True) is False

    def test_passes_in_strict_with_signing_ceremony(self, tmp_path: Path) -> None:
        from ceremony_log import CeremonyLog, CeremonyType
        log = CeremonyLog(tmp_path / "state" / "ceremony-log")
        log.append(
            CeremonyType.PACKAGE_SIGNING, actor="ci", actor_role="ADMIN",
            details={"manifest_version": "3.0", "key_id": "abc12345"},
        )
        assert _check_ceremony_log(tmp_path, strict=True) is True

    def test_fails_in_strict_without_signing_ceremony(self, tmp_path: Path) -> None:
        from ceremony_log import CeremonyLog, CeremonyType
        log = CeremonyLog(tmp_path / "state" / "ceremony-log")
        log.append(
            CeremonyType.RELEASE_APPROVAL, actor="alice", actor_role="ADMIN",
            details={"release_tag": "v1.0", "approval_notes": "ok"},
        )
        assert _check_ceremony_log(tmp_path, strict=True) is False

    def test_fails_with_tampered_ceremony_log(self, tmp_path: Path) -> None:
        from ceremony_log import CeremonyLog, CeremonyType
        log = CeremonyLog(tmp_path / "state" / "ceremony-log")
        log.append(
            CeremonyType.PACKAGE_SIGNING, actor="ci", actor_role="ADMIN",
            details={"manifest_version": "3.0", "key_id": "abc"},
        )
        lines = log.log_file.read_text().splitlines()
        entry = json.loads(lines[0])
        entry["actor"] = "mallory"
        lines[0] = json.dumps(entry)
        log.log_file.write_text("\n".join(lines) + "\n")
        assert _check_ceremony_log(tmp_path, strict=False) is False


# ---------------------------------------------------------------------------
# main() — integration tests via subprocess mock
# ---------------------------------------------------------------------------

class TestMainFailureModes:
    def _run_main(self, argv: list[str], monkeypatch, tmp_path: Path) -> int:
        """Run main() with REPO_ROOT monkeypatched to tmp_path."""
        import run_release_gate as rg
        monkeypatch.setattr(rg, "REPO_ROOT", tmp_path)
        return rg.main(argv)

    def test_quick_mode_returns_nonzero_on_bad_workflow(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        import run_release_gate as rg
        monkeypatch.setattr(rg, "REPO_ROOT", tmp_path)
        # _run calls subprocess — patch it to return failure for workflow validate
        def fake_run(label, cmd, cwd=None):
            return False
        monkeypatch.setattr(rg, "_run", fake_run)
        code = rg.main(["--quick"])
        assert code == 1

    def test_all_checks_pass_returns_zero(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        import run_release_gate as rg
        monkeypatch.setattr(rg, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(rg, "_run", lambda label, cmd, cwd=None: True)
        monkeypatch.setattr(rg, "_grep_oanda", lambda repo_root: True)
        monkeypatch.setattr(rg, "_check_forbidden_language", lambda repo_root: True)
        monkeypatch.setattr(rg, "_check_audit_log_chain", lambda repo_root: True)
        monkeypatch.setattr(rg, "_check_ceremony_log", lambda repo_root, strict=False: True)
        code = rg.main(["--quick"])
        assert code == 0

    def test_oanda_violation_returns_nonzero(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        import run_release_gate as rg
        monkeypatch.setattr(rg, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(rg, "_run", lambda label, cmd, cwd=None: True)
        monkeypatch.setattr(rg, "_grep_oanda", lambda repo_root: False)
        monkeypatch.setattr(rg, "_check_forbidden_language", lambda repo_root: True)
        monkeypatch.setattr(rg, "_check_audit_log_chain", lambda repo_root: True)
        monkeypatch.setattr(rg, "_check_ceremony_log", lambda repo_root, strict=False: True)
        code = rg.main(["--quick"])
        assert code == 1

    def test_forbidden_language_violation_returns_nonzero(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        import run_release_gate as rg
        monkeypatch.setattr(rg, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(rg, "_run", lambda label, cmd, cwd=None: True)
        monkeypatch.setattr(rg, "_grep_oanda", lambda repo_root: True)
        monkeypatch.setattr(rg, "_check_forbidden_language", lambda repo_root: False)
        monkeypatch.setattr(rg, "_check_audit_log_chain", lambda repo_root: True)
        monkeypatch.setattr(rg, "_check_ceremony_log", lambda repo_root, strict=False: True)
        code = rg.main(["--quick"])
        assert code == 1

    def test_strict_mode_respected(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        import run_release_gate as rg
        monkeypatch.setattr(rg, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(rg, "_run", lambda label, cmd, cwd=None: True)
        monkeypatch.setattr(rg, "_grep_oanda", lambda repo_root: True)
        monkeypatch.setattr(rg, "_check_forbidden_language", lambda repo_root: True)
        monkeypatch.setattr(rg, "_check_audit_log_chain", lambda repo_root: True)
        # strict mode — ceremony log returns False
        ceremony_calls = []
        def mock_ceremony(repo_root, strict=False):
            ceremony_calls.append(strict)
            return False
        monkeypatch.setattr(rg, "_check_ceremony_log", mock_ceremony)
        code = rg.main(["--quick", "--strict"])
        assert code == 1
        assert True in ceremony_calls  # strict=True was passed
