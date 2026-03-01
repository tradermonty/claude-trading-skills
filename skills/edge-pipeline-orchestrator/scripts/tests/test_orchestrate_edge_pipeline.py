"""Tests for edge-pipeline-orchestrator."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent),
)

from orchestrate_edge_pipeline import (
    SCRIPT_PATHS,
    EdgePipelineError,
    ReviewLoopResult,
    TrackedDraft,
    apply_revisions,
    build_export_ticket,
    downgrade_to_research_probe,
    load_drafts_from_dir,
    load_reviews_from_dir,
    run_review_loop,
    run_stage,
    should_export,
)


# ---------------------------------------------------------------------------
# TrackedDraft tests
# ---------------------------------------------------------------------------
class TestTrackedDraft:
    def test_tracked_draft_preserves_file_path(
        self, tmp_path: Path, sample_draft_pass: dict
    ) -> None:
        draft_path = tmp_path / "draft_abc.yaml"
        draft_path.write_text(yaml.safe_dump(sample_draft_pass, sort_keys=False))
        td = TrackedDraft(
            draft_id=sample_draft_pass["id"],
            file_path=draft_path,
            verdict="PASS",
            export_eligible=True,
            confidence_score=82,
        )
        assert td.file_path == draft_path
        assert td.file_path.exists()

    def test_tracked_draft_fields(self) -> None:
        td = TrackedDraft(
            draft_id="draft_abc",
            file_path=Path("/tmp/draft_abc.yaml"),
            verdict="REVISE",
            export_eligible=False,
            confidence_score=55,
        )
        assert td.draft_id == "draft_abc"
        assert td.verdict == "REVISE"
        assert not td.export_eligible
        assert td.confidence_score == 55


# ---------------------------------------------------------------------------
# Review loop tests
# ---------------------------------------------------------------------------
class TestReviewLoop:
    def _make_drafts_and_reviews(
        self,
        tmp_path: Path,
        drafts: list[dict],
        reviews_by_iter: list[list[dict]],
    ) -> tuple[Path, list[Path]]:
        """Helper to write draft files and review iteration directories."""
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir(exist_ok=True)
        for draft in drafts:
            (drafts_dir / f"{draft['id']}.yaml").write_text(yaml.safe_dump(draft, sort_keys=False))

        review_dirs: list[Path] = []
        for i, reviews in enumerate(reviews_by_iter):
            rd = tmp_path / f"reviews_iter_{i}"
            rd.mkdir(exist_ok=True)
            for review in reviews:
                (rd / f"{review['draft_id']}_review.yaml").write_text(
                    yaml.safe_dump(review, sort_keys=False)
                )
            review_dirs.append(rd)
        return drafts_dir, review_dirs

    @patch("orchestrate_edge_pipeline.run_stage")
    def test_review_loop_exits_on_all_pass(
        self,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        sample_draft_pass: dict,
    ) -> None:
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        (drafts_dir / f"{sample_draft_pass['id']}.yaml").write_text(
            yaml.safe_dump(sample_draft_pass, sort_keys=False)
        )
        review_dir = tmp_path / "reviews_iter_0"
        review_dir.mkdir()
        review = {
            "draft_id": sample_draft_pass["id"],
            "verdict": "PASS",
            "confidence_score": 85,
            "revision_instructions": [],
        }
        (review_dir / f"{sample_draft_pass['id']}_review.yaml").write_text(
            yaml.safe_dump(review, sort_keys=False)
        )

        def side_effect(stage: str, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="[OK]", stderr="")

        mock_run_stage.side_effect = side_effect

        result = run_review_loop(
            drafts_dir=drafts_dir,
            review_output_base=tmp_path,
            max_iterations=2,
        )
        assert len(result.passed) == 1
        assert len(result.rejected) == 0
        assert len(result.downgraded) == 0
        assert result.passed[0].draft_id == sample_draft_pass["id"]

    @patch("orchestrate_edge_pipeline.run_stage")
    def test_review_loop_forwards_strict_export_to_review_stage(
        self,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        sample_draft_pass: dict,
    ) -> None:
        """strict_export=True adds --strict-export to review stage args."""
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        (drafts_dir / f"{sample_draft_pass['id']}.yaml").write_text(
            yaml.safe_dump(sample_draft_pass, sort_keys=False)
        )
        review_dir = tmp_path / "reviews_iter_0"
        review_dir.mkdir()
        review = {
            "draft_id": sample_draft_pass["id"],
            "verdict": "PASS",
            "confidence_score": 85,
            "revision_instructions": [],
        }
        (review_dir / f"{sample_draft_pass['id']}_review.yaml").write_text(
            yaml.safe_dump(review, sort_keys=False)
        )

        def side_effect(stage: str, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="[OK]", stderr="")

        mock_run_stage.side_effect = side_effect

        run_review_loop(
            drafts_dir=drafts_dir,
            review_output_base=tmp_path,
            max_iterations=2,
            strict_export=True,
        )

        review_calls = [c for c in mock_run_stage.call_args_list if c[0][0] == "review"]
        assert len(review_calls) >= 1
        review_args = review_calls[0][0][1]
        assert "--strict-export" in review_args

    @patch("orchestrate_edge_pipeline.run_stage")
    def test_review_loop_max_iterations(
        self,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        sample_draft_revise: dict,
    ) -> None:
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        (drafts_dir / f"{sample_draft_revise['id']}.yaml").write_text(
            yaml.safe_dump(sample_draft_revise, sort_keys=False)
        )

        call_count = 0

        def side_effect(stage: str, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            nonlocal call_count
            if stage == "review":
                # Write REVISE review for each iteration
                for arg_idx, arg in enumerate(args):
                    if arg == "--output-dir":
                        out_dir = Path(args[arg_idx + 1])
                        out_dir.mkdir(parents=True, exist_ok=True)
                        review = {
                            "draft_id": sample_draft_revise["id"],
                            "verdict": "REVISE",
                            "confidence_score": 50,
                            "revision_instructions": ["Reduce entry conditions"],
                        }
                        (out_dir / f"{sample_draft_revise['id']}_review.yaml").write_text(
                            yaml.safe_dump(review, sort_keys=False)
                        )
                        break
                call_count += 1
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="[OK]", stderr="")

        mock_run_stage.side_effect = side_effect

        result = run_review_loop(
            drafts_dir=drafts_dir,
            review_output_base=tmp_path,
            max_iterations=2,
        )
        assert len(result.passed) == 0
        assert len(result.rejected) == 0
        assert len(result.downgraded) == 1
        assert result.downgraded[0] == sample_draft_revise["id"]

    @patch("orchestrate_edge_pipeline.run_stage")
    def test_reject_not_revised(
        self,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        sample_draft_reject: dict,
    ) -> None:
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        (drafts_dir / f"{sample_draft_reject['id']}.yaml").write_text(
            yaml.safe_dump(sample_draft_reject, sort_keys=False)
        )

        def side_effect(stage: str, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            if stage == "review":
                for arg_idx, arg in enumerate(args):
                    if arg == "--output-dir":
                        out_dir = Path(args[arg_idx + 1])
                        out_dir.mkdir(parents=True, exist_ok=True)
                        review = {
                            "draft_id": sample_draft_reject["id"],
                            "verdict": "REJECT",
                            "confidence_score": 15,
                            "revision_instructions": [],
                        }
                        (out_dir / f"{sample_draft_reject['id']}_review.yaml").write_text(
                            yaml.safe_dump(review, sort_keys=False)
                        )
                        break
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="[OK]", stderr="")

        mock_run_stage.side_effect = side_effect

        result = run_review_loop(
            drafts_dir=drafts_dir,
            review_output_base=tmp_path,
            max_iterations=2,
        )
        assert len(result.rejected) == 1
        assert len(result.passed) == 0
        assert result.rejected[0].draft_id == sample_draft_reject["id"]

    @patch("orchestrate_edge_pipeline.run_stage")
    def test_pass_accumulated_across_iterations(
        self,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        sample_draft_pass: dict,
        sample_draft_revise: dict,
    ) -> None:
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        for draft in [sample_draft_pass, sample_draft_revise]:
            (drafts_dir / f"{draft['id']}.yaml").write_text(yaml.safe_dump(draft, sort_keys=False))

        iteration = [0]

        def side_effect(stage: str, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            if stage == "review":
                for arg_idx, arg in enumerate(args):
                    if arg == "--output-dir":
                        out_dir = Path(args[arg_idx + 1])
                        out_dir.mkdir(parents=True, exist_ok=True)
                        if iteration[0] == 0:
                            # iter 0: pass one, revise the other
                            r1 = {
                                "draft_id": sample_draft_pass["id"],
                                "verdict": "PASS",
                                "confidence_score": 85,
                                "revision_instructions": [],
                            }
                            r2 = {
                                "draft_id": sample_draft_revise["id"],
                                "verdict": "REVISE",
                                "confidence_score": 50,
                                "revision_instructions": ["Reduce entry conditions"],
                            }
                            (out_dir / f"{sample_draft_pass['id']}_review.yaml").write_text(
                                yaml.safe_dump(r1, sort_keys=False)
                            )
                            (out_dir / f"{sample_draft_revise['id']}_review.yaml").write_text(
                                yaml.safe_dump(r2, sort_keys=False)
                            )
                        else:
                            # iter 1: pass the revised one
                            r2 = {
                                "draft_id": sample_draft_revise["id"],
                                "verdict": "PASS",
                                "confidence_score": 78,
                                "revision_instructions": [],
                            }
                            (out_dir / f"{sample_draft_revise['id']}_review.yaml").write_text(
                                yaml.safe_dump(r2, sort_keys=False)
                            )
                        iteration[0] += 1
                        break
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="[OK]", stderr="")

        mock_run_stage.side_effect = side_effect

        result = run_review_loop(
            drafts_dir=drafts_dir,
            review_output_base=tmp_path,
            max_iterations=2,
        )
        assert len(result.passed) == 2
        passed_ids = {td.draft_id for td in result.passed}
        assert sample_draft_pass["id"] in passed_ids
        assert sample_draft_revise["id"] in passed_ids

    @patch("orchestrate_edge_pipeline.run_stage")
    def test_reject_accumulated_across_iterations(
        self,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        sample_draft_reject: dict,
        sample_draft_revise: dict,
    ) -> None:
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        for draft in [sample_draft_reject, sample_draft_revise]:
            (drafts_dir / f"{draft['id']}.yaml").write_text(yaml.safe_dump(draft, sort_keys=False))

        iteration = [0]

        def side_effect(stage: str, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            if stage == "review":
                for arg_idx, arg in enumerate(args):
                    if arg == "--output-dir":
                        out_dir = Path(args[arg_idx + 1])
                        out_dir.mkdir(parents=True, exist_ok=True)
                        if iteration[0] == 0:
                            r1 = {
                                "draft_id": sample_draft_reject["id"],
                                "verdict": "REJECT",
                                "confidence_score": 15,
                                "revision_instructions": [],
                            }
                            r2 = {
                                "draft_id": sample_draft_revise["id"],
                                "verdict": "REVISE",
                                "confidence_score": 50,
                                "revision_instructions": ["Add volume filter"],
                            }
                            (out_dir / f"{sample_draft_reject['id']}_review.yaml").write_text(
                                yaml.safe_dump(r1, sort_keys=False)
                            )
                            (out_dir / f"{sample_draft_revise['id']}_review.yaml").write_text(
                                yaml.safe_dump(r2, sort_keys=False)
                            )
                        else:
                            r2 = {
                                "draft_id": sample_draft_revise["id"],
                                "verdict": "REJECT",
                                "confidence_score": 30,
                                "revision_instructions": [],
                            }
                            (out_dir / f"{sample_draft_revise['id']}_review.yaml").write_text(
                                yaml.safe_dump(r2, sort_keys=False)
                            )
                        iteration[0] += 1
                        break
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="[OK]", stderr="")

        mock_run_stage.side_effect = side_effect

        result = run_review_loop(
            drafts_dir=drafts_dir,
            review_output_base=tmp_path,
            max_iterations=2,
        )
        assert len(result.rejected) == 2
        rejected_ids = {td.draft_id for td in result.rejected}
        assert sample_draft_reject["id"] in rejected_ids
        assert sample_draft_revise["id"] in rejected_ids

    @patch("orchestrate_edge_pipeline.run_stage")
    def test_only_revise_in_next_iteration(
        self,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        sample_draft_pass: dict,
        sample_draft_revise: dict,
        sample_draft_reject: dict,
    ) -> None:
        """Only REVISE drafts should be re-reviewed in the next iteration."""
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        for draft in [sample_draft_pass, sample_draft_revise, sample_draft_reject]:
            (drafts_dir / f"{draft['id']}.yaml").write_text(yaml.safe_dump(draft, sort_keys=False))

        iteration = [0]
        iter1_draft_ids: list[str] = []

        def side_effect(stage: str, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            if stage == "review":
                drafts_dir_arg = None
                out_dir_arg = None
                for i, arg in enumerate(args):
                    if arg == "--drafts-dir" and i + 1 < len(args):
                        drafts_dir_arg = Path(args[i + 1])
                    if arg == "--output-dir" and i + 1 < len(args):
                        out_dir_arg = Path(args[i + 1])

                if out_dir_arg:
                    out_dir_arg.mkdir(parents=True, exist_ok=True)

                if iteration[0] == 0:
                    # iter 0: PASS, REVISE, REJECT
                    for draft_id, verdict, score in [
                        (sample_draft_pass["id"], "PASS", 85),
                        (sample_draft_revise["id"], "REVISE", 50),
                        (sample_draft_reject["id"], "REJECT", 15),
                    ]:
                        review = {
                            "draft_id": draft_id,
                            "verdict": verdict,
                            "confidence_score": score,
                            "revision_instructions": ["Reduce entry conditions"]
                            if verdict == "REVISE"
                            else [],
                        }
                        if out_dir_arg:
                            (out_dir_arg / f"{draft_id}_review.yaml").write_text(
                                yaml.safe_dump(review, sort_keys=False)
                            )
                else:
                    # iter 1: Record which drafts are being reviewed
                    if drafts_dir_arg and drafts_dir_arg.exists():
                        for f in drafts_dir_arg.glob("*.yaml"):
                            draft_data = yaml.safe_load(f.read_text())
                            if isinstance(draft_data, dict):
                                iter1_draft_ids.append(draft_data["id"])
                    # PASS the revised draft
                    review = {
                        "draft_id": sample_draft_revise["id"],
                        "verdict": "PASS",
                        "confidence_score": 75,
                        "revision_instructions": [],
                    }
                    if out_dir_arg:
                        (out_dir_arg / f"{sample_draft_revise['id']}_review.yaml").write_text(
                            yaml.safe_dump(review, sort_keys=False)
                        )

                iteration[0] += 1
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="[OK]", stderr="")

        mock_run_stage.side_effect = side_effect

        run_review_loop(
            drafts_dir=drafts_dir,
            review_output_base=tmp_path,
            max_iterations=2,
        )
        # Only the REVISE draft should appear in iter 1
        assert len(iter1_draft_ids) == 1
        assert iter1_draft_ids[0] == sample_draft_revise["id"]

    @patch("orchestrate_edge_pipeline.run_stage")
    def test_revise_downgraded_after_max(
        self,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        sample_draft_revise: dict,
    ) -> None:
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        (drafts_dir / f"{sample_draft_revise['id']}.yaml").write_text(
            yaml.safe_dump(sample_draft_revise, sort_keys=False)
        )

        def side_effect(stage: str, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            if stage == "review":
                for arg_idx, arg in enumerate(args):
                    if arg == "--output-dir":
                        out_dir = Path(args[arg_idx + 1])
                        out_dir.mkdir(parents=True, exist_ok=True)
                        review = {
                            "draft_id": sample_draft_revise["id"],
                            "verdict": "REVISE",
                            "confidence_score": 50,
                            "revision_instructions": ["Reduce entry conditions"],
                        }
                        (out_dir / f"{sample_draft_revise['id']}_review.yaml").write_text(
                            yaml.safe_dump(review, sort_keys=False)
                        )
                        break
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="[OK]", stderr="")

        mock_run_stage.side_effect = side_effect

        result = run_review_loop(
            drafts_dir=drafts_dir,
            review_output_base=tmp_path,
            max_iterations=2,
        )
        assert sample_draft_revise["id"] in result.downgraded

    @patch("orchestrate_edge_pipeline.run_stage")
    def test_downgrade_sets_research_probe(
        self,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        sample_draft_revise: dict,
    ) -> None:
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        draft_path = drafts_dir / f"{sample_draft_revise['id']}.yaml"
        draft_path.write_text(yaml.safe_dump(sample_draft_revise, sort_keys=False))

        def side_effect(stage: str, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            if stage == "review":
                for arg_idx, arg in enumerate(args):
                    if arg == "--output-dir":
                        out_dir = Path(args[arg_idx + 1])
                        out_dir.mkdir(parents=True, exist_ok=True)
                        review = {
                            "draft_id": sample_draft_revise["id"],
                            "verdict": "REVISE",
                            "confidence_score": 50,
                            "revision_instructions": ["Reduce entry conditions"],
                        }
                        (out_dir / f"{sample_draft_revise['id']}_review.yaml").write_text(
                            yaml.safe_dump(review, sort_keys=False)
                        )
                        break
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="[OK]", stderr="")

        mock_run_stage.side_effect = side_effect

        run_review_loop(
            drafts_dir=drafts_dir,
            review_output_base=tmp_path,
            max_iterations=2,
        )
        # Read the downgraded draft file and verify
        downgraded_draft = yaml.safe_load(draft_path.read_text())
        assert downgraded_draft["variant"] == "research_probe"
        assert downgraded_draft["export_ready_v1"] is False


# ---------------------------------------------------------------------------
# Export logic tests
# ---------------------------------------------------------------------------
class TestExportLogic:
    def test_export_eligible_pass_exportable(self, sample_draft_pass: dict) -> None:
        assert should_export(sample_draft_pass) is True

    def test_export_skip_pass_research_only(self, sample_draft_reject: dict) -> None:
        # research_only entry_family, export_ready_v1=False
        assert should_export(sample_draft_reject) is False

    def test_export_skip_pass_wrong_family(self, sample_draft_pass: dict) -> None:
        draft = dict(sample_draft_pass)
        draft["entry_family"] = "research_only"
        assert should_export(draft) is False

    def test_export_skip_not_export_ready(self, sample_draft_pass: dict) -> None:
        draft = dict(sample_draft_pass)
        draft["export_ready_v1"] = False
        assert should_export(draft) is False

    def test_export_gap_up_eligible(self, sample_draft_gap_up: dict) -> None:
        assert should_export(sample_draft_gap_up) is True

    @patch("orchestrate_edge_pipeline.run_stage")
    def test_export_uses_strategies_dir_arg(
        self,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        sample_draft_pass: dict,
    ) -> None:
        mock_run_stage.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK]", stderr=""
        )
        strategies_dir = tmp_path / "strategies"
        strategies_dir.mkdir()
        ticket_path = tmp_path / "ticket.yaml"
        ticket_path.write_text(
            yaml.safe_dump(build_export_ticket(sample_draft_pass), sort_keys=False)
        )

        from orchestrate_edge_pipeline import export_draft

        export_draft(
            draft=sample_draft_pass,
            draft_path=tmp_path / f"{sample_draft_pass['id']}.yaml",
            strategies_dir=strategies_dir,
            exportable_tickets_dir=None,
            dry_run=False,
        )
        # Verify --strategies-dir is in the call args
        call_args = mock_run_stage.call_args
        assert call_args is not None
        args_list = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("args", [])
        assert "--strategies-dir" in args_list
        assert str(strategies_dir) in args_list

    def test_export_uses_pregenerated_ticket(
        self,
        tmp_path: Path,
        sample_draft_pass: dict,
        exportable_tickets_dir: Path,
    ) -> None:
        """Pre-generated ticket should be preferred when available."""
        ticket_id = sample_draft_pass["id"].replace("draft_", "edge_")
        expected_path = exportable_tickets_dir / f"{ticket_id}.yaml"
        assert expected_path.exists()

        # Verify the pre-generated ticket has the right ID
        ticket_data = yaml.safe_load(expected_path.read_text())
        assert ticket_data["id"] == ticket_id

    @patch("orchestrate_edge_pipeline.run_stage")
    def test_export_generates_ticket_for_revised(
        self,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        sample_draft_revise: dict,
    ) -> None:
        """Revised drafts without pre-generated tickets get build_export_ticket()."""
        mock_run_stage.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK]", stderr=""
        )
        strategies_dir = tmp_path / "strategies"
        strategies_dir.mkdir()

        # No exportable_tickets_dir → must generate ticket
        from orchestrate_edge_pipeline import export_draft

        export_draft(
            draft=sample_draft_revise,
            draft_path=tmp_path / f"{sample_draft_revise['id']}.yaml",
            strategies_dir=strategies_dir,
            exportable_tickets_dir=None,
            dry_run=False,
        )
        assert mock_run_stage.called
        # Verify ticket was generated (written to tmp path)
        call_args = mock_run_stage.call_args
        args_list = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("args", [])
        assert "--ticket" in args_list

    def test_build_export_ticket_schema(self, sample_draft_pass: dict) -> None:
        ticket = build_export_ticket(sample_draft_pass)
        assert ticket["id"] == sample_draft_pass["id"].replace("draft_", "edge_")
        assert ticket["name"] == sample_draft_pass["name"]
        assert "description" in ticket
        assert ticket["hypothesis_type"] == sample_draft_pass["hypothesis_type"]
        assert ticket["entry_family"] == sample_draft_pass["entry_family"]
        assert ticket["mechanism_tag"] == sample_draft_pass["mechanism_tag"]
        assert ticket["regime"] == sample_draft_pass["regime"]
        assert ticket["holding_horizon"] == "20D"
        assert "conditions" in ticket["entry"]
        assert "trend_filter" in ticket["entry"]
        assert "risk" in ticket
        assert "exit" in ticket
        assert ticket["exit"]["stop_loss_pct"] == sample_draft_pass["exit"]["stop_loss_pct"]
        assert ticket["exit"]["take_profit_rr"] == sample_draft_pass["exit"]["take_profit_rr"]
        assert ticket["cost_model"]["commission_per_share"] == 0.0
        assert ticket["cost_model"]["slippage_bps"] == 5


# ---------------------------------------------------------------------------
# File path management tests
# ---------------------------------------------------------------------------
class TestFilePathManagement:
    def test_export_reads_from_tracked_path(self, tmp_path: Path, sample_draft_pass: dict) -> None:
        draft_path = tmp_path / f"{sample_draft_pass['id']}.yaml"
        draft_path.write_text(yaml.safe_dump(sample_draft_pass, sort_keys=False))
        td = TrackedDraft(
            draft_id=sample_draft_pass["id"],
            file_path=draft_path,
            verdict="PASS",
            export_eligible=True,
            confidence_score=85,
        )
        loaded = yaml.safe_load(td.file_path.read_text())
        assert loaded["id"] == sample_draft_pass["id"]

    @patch("orchestrate_edge_pipeline.run_stage")
    def test_pass_from_iter0_accessible_after_iter1(
        self,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        sample_draft_pass: dict,
        sample_draft_revise: dict,
    ) -> None:
        """A draft that PASSed in iter 0 should still have accessible file path after iter 1."""
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        for draft in [sample_draft_pass, sample_draft_revise]:
            (drafts_dir / f"{draft['id']}.yaml").write_text(yaml.safe_dump(draft, sort_keys=False))

        iteration = [0]

        def side_effect(stage: str, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            if stage == "review":
                for arg_idx, arg in enumerate(args):
                    if arg == "--output-dir":
                        out_dir = Path(args[arg_idx + 1])
                        out_dir.mkdir(parents=True, exist_ok=True)
                        if iteration[0] == 0:
                            r1 = {
                                "draft_id": sample_draft_pass["id"],
                                "verdict": "PASS",
                                "confidence_score": 85,
                                "revision_instructions": [],
                            }
                            r2 = {
                                "draft_id": sample_draft_revise["id"],
                                "verdict": "REVISE",
                                "confidence_score": 50,
                                "revision_instructions": ["Add volume filter"],
                            }
                            (out_dir / f"{sample_draft_pass['id']}_review.yaml").write_text(
                                yaml.safe_dump(r1, sort_keys=False)
                            )
                            (out_dir / f"{sample_draft_revise['id']}_review.yaml").write_text(
                                yaml.safe_dump(r2, sort_keys=False)
                            )
                        else:
                            r2 = {
                                "draft_id": sample_draft_revise["id"],
                                "verdict": "PASS",
                                "confidence_score": 70,
                                "revision_instructions": [],
                            }
                            (out_dir / f"{sample_draft_revise['id']}_review.yaml").write_text(
                                yaml.safe_dump(r2, sort_keys=False)
                            )
                        iteration[0] += 1
                        break
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="[OK]", stderr="")

        mock_run_stage.side_effect = side_effect

        result = run_review_loop(
            drafts_dir=drafts_dir,
            review_output_base=tmp_path,
            max_iterations=2,
        )
        # Both passed drafts should have accessible file paths
        for td in result.passed:
            assert td.file_path.exists(), f"File path missing for {td.draft_id}: {td.file_path}"


# ---------------------------------------------------------------------------
# Revision logic tests
# ---------------------------------------------------------------------------
class TestRevisionLogic:
    def test_apply_revision_reduces_conditions(self, sample_draft_revise: dict) -> None:
        original_count = len(sample_draft_revise["entry"]["conditions"])
        assert original_count > 5

        revised = apply_revisions(
            draft=sample_draft_revise,
            instructions=["Reduce entry conditions"],
        )
        assert len(revised["entry"]["conditions"]) == 5

    def test_apply_revision_adds_volume_filter(self, sample_draft_pass: dict) -> None:
        original_conditions = list(sample_draft_pass["entry"]["conditions"])
        revised = apply_revisions(
            draft=sample_draft_pass,
            instructions=["Add volume filter"],
        )
        assert "avg_volume > 500000" in revised["entry"]["conditions"]
        assert len(revised["entry"]["conditions"]) == len(original_conditions) + 1

    def test_apply_revision_rounds_thresholds(self) -> None:
        draft: dict[str, Any] = {
            "id": "test_draft",
            "entry": {
                "conditions": ["rsi > 50.7", "adx > 25.3", "close > 100"],
                "trend_filter": [],
            },
            "variant": "core",
            "export_ready_v1": True,
        }
        revised = apply_revisions(draft, instructions=["Round precise thresholds"])
        # Numbers with decimals should be rounded
        conditions = revised["entry"]["conditions"]
        assert "rsi > 51" in conditions
        assert "adx > 25" in conditions
        # Integer values unchanged
        assert "close > 100" in conditions

    def test_apply_revision_preserves_variant(self, sample_draft_revise: dict) -> None:
        original_variant = sample_draft_revise["variant"]
        revised = apply_revisions(sample_draft_revise, instructions=["Reduce entry conditions"])
        assert revised["variant"] == original_variant

    def test_apply_revision_preserves_export_ready(self, sample_draft_revise: dict) -> None:
        original_export_ready = sample_draft_revise["export_ready_v1"]
        revised = apply_revisions(sample_draft_revise, instructions=["Add volume filter"])
        assert revised["export_ready_v1"] == original_export_ready


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------
class TestCLI:
    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_cli_full_pipeline_with_tickets_dir(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        tickets_dir: Path,
        hints_file: Path,
        concepts_file: Path,
    ) -> None:
        from orchestrate_edge_pipeline import main

        mock_run_stage.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK]", stderr=""
        )
        mock_review_loop.return_value = ReviewLoopResult(passed=[], rejected=[], downgraded=[])

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--tickets-dir",
                str(tickets_dir),
                "--output-dir",
                str(output_dir),
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        # Verify manifest was written
        manifest_path = output_dir / "pipeline_run_manifest.json"
        assert manifest_path.exists()

    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_cli_from_ohlcv(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
    ) -> None:
        from orchestrate_edge_pipeline import main

        ohlcv_path = tmp_path / "ohlcv.csv"
        ohlcv_path.write_text(
            "symbol,timestamp,open,high,low,close,volume\nAAPL,2026-01-01,150,155,149,154,1000000\n"
        )

        def side_effect(stage: str, args: list[str], **kw: Any) -> subprocess.CompletedProcess:
            if stage == "auto_detect":
                # Simulate auto_detect creating market_summary and anomalies
                tickets_out = None
                for i, a in enumerate(args):
                    if a == "--output-dir":
                        tickets_out = Path(args[i + 1])
                        break
                if tickets_out:
                    tickets_out.mkdir(parents=True, exist_ok=True)
                    (tickets_out / "market_summary.json").write_text('{"regime": "Neutral"}')
                    (tickets_out / "anomalies.json").write_text('{"anomalies": []}')
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="[OK]", stderr="")

        mock_run_stage.side_effect = side_effect
        mock_review_loop.return_value = ReviewLoopResult(passed=[], rejected=[], downgraded=[])

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--from-ohlcv",
                str(ohlcv_path),
                "--output-dir",
                str(output_dir),
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        # auto_detect should have been called
        stage_calls = [c[0][0] for c in mock_run_stage.call_args_list]
        assert "auto_detect" in stage_calls

        # hints stage should receive auto_detect's market_summary and anomalies
        hints_calls = [c for c in mock_run_stage.call_args_list if c[0][0] == "hints"]
        assert len(hints_calls) == 1
        hints_args = hints_calls[0][0][1]
        assert "--market-summary" in hints_args
        assert "--anomalies" in hints_args

    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_cli_resume_from_drafts(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        drafts_dir: Path,
    ) -> None:
        from orchestrate_edge_pipeline import main

        mock_run_stage.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK]", stderr=""
        )
        mock_review_loop.return_value = ReviewLoopResult(passed=[], rejected=[], downgraded=[])

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--resume-from",
                "drafts",
                "--drafts-dir",
                str(drafts_dir),
                "--output-dir",
                str(output_dir),
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        # Earlier stages should NOT be called
        stage_calls = [c[0][0] for c in mock_run_stage.call_args_list]
        assert "auto_detect" not in stage_calls
        assert "hints" not in stage_calls
        assert "concepts" not in stage_calls

    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_cli_review_only(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        drafts_dir: Path,
    ) -> None:
        from orchestrate_edge_pipeline import main

        mock_review_loop.return_value = ReviewLoopResult(passed=[], rejected=[], downgraded=[])

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--review-only",
                "--drafts-dir",
                str(drafts_dir),
                "--output-dir",
                str(output_dir),
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        # run_stage should not be called for early stages
        stage_calls = [c[0][0] for c in mock_run_stage.call_args_list]
        assert "auto_detect" not in stage_calls
        assert "hints" not in stage_calls
        assert "concepts" not in stage_calls
        assert "drafts" not in stage_calls
        # review_loop must be called
        assert mock_review_loop.called

    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_dry_run_no_export(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        sample_draft_pass: dict,
        drafts_dir: Path,
    ) -> None:
        from orchestrate_edge_pipeline import main

        draft_path = drafts_dir / f"{sample_draft_pass['id']}.yaml"

        mock_review_loop.return_value = ReviewLoopResult(
            passed=[
                TrackedDraft(
                    draft_id=sample_draft_pass["id"],
                    file_path=draft_path,
                    verdict="PASS",
                    export_eligible=True,
                    confidence_score=85,
                )
            ],
            rejected=[],
            downgraded=[],
        )

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--review-only",
                "--drafts-dir",
                str(drafts_dir),
                "--output-dir",
                str(output_dir),
                "--dry-run",
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        # Export stage should NOT have been called
        stage_calls = [c[0][0] for c in mock_run_stage.call_args_list]
        assert "export" not in stage_calls

    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_pipeline_manifest_complete(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        tickets_dir: Path,
        sample_draft_pass: dict,
    ) -> None:
        from orchestrate_edge_pipeline import main

        mock_run_stage.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK]", stderr=""
        )
        draft_path = tmp_path / "output" / "drafts" / f"{sample_draft_pass['id']}.yaml"

        mock_review_loop.return_value = ReviewLoopResult(
            passed=[
                TrackedDraft(
                    draft_id=sample_draft_pass["id"],
                    file_path=draft_path,
                    verdict="PASS",
                    export_eligible=True,
                    confidence_score=85,
                ),
            ],
            rejected=[],
            downgraded=[],
        )

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--tickets-dir",
                str(tickets_dir),
                "--output-dir",
                str(output_dir),
                "--dry-run",
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        manifest_path = output_dir / "pipeline_run_manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert "run_id" in manifest
        assert manifest["run_id"].startswith("edge_pipeline_")
        assert "started_at_utc" in manifest
        assert "status" in manifest
        assert manifest["status"] == "completed"
        assert "input" in manifest
        assert "stages" in manifest


# ---------------------------------------------------------------------------
# run_stage tests
# ---------------------------------------------------------------------------
class TestRunStage:
    @patch("subprocess.run")
    def test_run_stage_subprocess(self, mock_subprocess: MagicMock) -> None:
        mock_subprocess.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK] hints=9", stderr=""
        )
        result = run_stage("hints", ["--market-summary", "/tmp/ms.json"])
        assert result.returncode == 0
        # Verify subprocess was called with the correct script path
        call_args = mock_subprocess.call_args
        cmd = call_args[0][0]
        assert SCRIPT_PATHS["hints"] in cmd[1]

    @patch("subprocess.run")
    def test_run_stage_failure(self, mock_subprocess: MagicMock) -> None:
        mock_subprocess.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="[ERROR] file not found"
        )
        with pytest.raises(EdgePipelineError, match="stage 'hints' failed"):
            run_stage("hints", ["--market-summary", "/tmp/ms.json"])

    @patch("subprocess.run")
    def test_run_stage_unknown_stage(self, mock_subprocess: MagicMock) -> None:
        with pytest.raises(EdgePipelineError, match="unknown stage"):
            run_stage("nonexistent", [])


# ---------------------------------------------------------------------------
# Downgrade helper tests
# ---------------------------------------------------------------------------
class TestDowngrade:
    def test_downgrade_to_research_probe(self, sample_draft_revise: dict) -> None:
        downgraded = downgrade_to_research_probe(sample_draft_revise)
        assert downgraded["variant"] == "research_probe"
        assert downgraded["export_ready_v1"] is False

    def test_downgrade_preserves_other_fields(self, sample_draft_revise: dict) -> None:
        downgraded = downgrade_to_research_probe(sample_draft_revise)
        assert downgraded["id"] == sample_draft_revise["id"]
        assert downgraded["entry_family"] == sample_draft_revise["entry_family"]
        assert downgraded["hypothesis_type"] == sample_draft_revise["hypothesis_type"]


# ---------------------------------------------------------------------------
# Load helpers tests
# ---------------------------------------------------------------------------
class TestLoadHelpers:
    def test_load_drafts_from_dir(self, drafts_dir: Path) -> None:
        drafts = load_drafts_from_dir(drafts_dir)
        assert len(drafts) == 3
        assert all(isinstance(d, dict) for d in drafts)
        ids = {d["id"] for d in drafts}
        assert len(ids) == 3

    def test_load_reviews_from_dir(self, reviews_dir: Path) -> None:
        reviews = load_reviews_from_dir(reviews_dir)
        assert len(reviews) == 3
        assert all(isinstance(r, dict) for r in reviews)
        verdicts = {r["verdict"] for r in reviews}
        assert verdicts == {"PASS", "REVISE", "REJECT"}

    def test_load_reviews_consolidated_format(self, tmp_path: Path) -> None:
        """Consolidated review.yaml (edge-strategy-reviewer output) is parsed."""
        consolidated = {
            "generated_at_utc": "2026-03-01T00:00:00+00:00",
            "source": {"drafts_dir": "/tmp", "draft_count": 2},
            "summary": {"total": 2, "PASS": 1, "REVISE": 1},
            "reviews": [
                {"draft_id": "draft_a", "verdict": "PASS", "confidence_score": 80},
                {"draft_id": "draft_b", "verdict": "REVISE", "confidence_score": 50},
            ],
        }
        review_dir = tmp_path / "reviews"
        review_dir.mkdir()
        (review_dir / "review.yaml").write_text(yaml.safe_dump(consolidated, sort_keys=False))
        reviews = load_reviews_from_dir(review_dir)
        assert len(reviews) == 2
        assert reviews[0]["draft_id"] == "draft_a"
        assert reviews[1]["draft_id"] == "draft_b"


# ---------------------------------------------------------------------------
# --strict-export forwarding tests
# ---------------------------------------------------------------------------
class TestStrictExportForwarding:
    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_strict_export_forwarded_to_review_loop(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        tickets_dir: Path,
    ) -> None:
        """--strict-export is forwarded to run_review_loop."""
        from orchestrate_edge_pipeline import main

        mock_run_stage.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK]", stderr=""
        )
        mock_review_loop.return_value = ReviewLoopResult(passed=[], rejected=[], downgraded=[])

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--tickets-dir",
                str(tickets_dir),
                "--strict-export",
                "--output-dir",
                str(output_dir),
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        mock_review_loop.assert_called_once()
        call_kwargs = mock_review_loop.call_args
        assert call_kwargs.kwargs.get("strict_export") is True or (
            len(call_kwargs.args) >= 4 and call_kwargs.args[3] is True
        )

    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_strict_export_not_forwarded_when_absent(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        tickets_dir: Path,
    ) -> None:
        """strict_export defaults to False when not specified."""
        from orchestrate_edge_pipeline import main

        mock_run_stage.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK]", stderr=""
        )
        mock_review_loop.return_value = ReviewLoopResult(passed=[], rejected=[], downgraded=[])

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--tickets-dir",
                str(tickets_dir),
                "--output-dir",
                str(output_dir),
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        mock_review_loop.assert_called_once()
        call_kwargs = mock_review_loop.call_args
        assert call_kwargs.kwargs.get("strict_export") is False or (len(call_kwargs.args) < 4)


# ---------------------------------------------------------------------------
# --max-synthetic-ratio forwarding tests
# ---------------------------------------------------------------------------
class TestMaxSyntheticRatioForwarding:
    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_max_synthetic_ratio_forwarded_to_concepts_stage(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        tickets_dir: Path,
    ) -> None:
        """--max-synthetic-ratio is forwarded to the concepts stage."""
        from orchestrate_edge_pipeline import main

        mock_run_stage.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK]", stderr=""
        )
        mock_review_loop.return_value = ReviewLoopResult(passed=[], rejected=[], downgraded=[])

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--tickets-dir",
                str(tickets_dir),
                "--max-synthetic-ratio",
                "1.5",
                "--output-dir",
                str(output_dir),
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        concepts_calls = [c for c in mock_run_stage.call_args_list if c[0][0] == "concepts"]
        assert len(concepts_calls) == 1
        concepts_args = concepts_calls[0][0][1]
        assert "--max-synthetic-ratio" in concepts_args
        assert "1.5" in concepts_args

    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_max_synthetic_ratio_absent_when_not_specified(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        tickets_dir: Path,
    ) -> None:
        """--max-synthetic-ratio should not appear in concepts args when not specified."""
        from orchestrate_edge_pipeline import main

        mock_run_stage.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK]", stderr=""
        )
        mock_review_loop.return_value = ReviewLoopResult(passed=[], rejected=[], downgraded=[])

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--tickets-dir",
                str(tickets_dir),
                "--output-dir",
                str(output_dir),
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        concepts_calls = [c for c in mock_run_stage.call_args_list if c[0][0] == "concepts"]
        assert len(concepts_calls) == 1
        concepts_args = concepts_calls[0][0][1]
        assert "--max-synthetic-ratio" not in concepts_args


# ---------------------------------------------------------------------------
# --overlap-threshold / --no-dedup forwarding tests
# ---------------------------------------------------------------------------
class TestDedupForwarding:
    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_overlap_threshold_forwarded_to_concepts(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        tickets_dir: Path,
    ) -> None:
        """--overlap-threshold should be forwarded to concepts stage."""
        from orchestrate_edge_pipeline import main

        mock_run_stage.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK]", stderr=""
        )
        mock_review_loop.return_value = ReviewLoopResult(passed=[], rejected=[], downgraded=[])

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--tickets-dir",
                str(tickets_dir),
                "--overlap-threshold",
                "0.6",
                "--output-dir",
                str(output_dir),
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        concepts_calls = [c for c in mock_run_stage.call_args_list if c[0][0] == "concepts"]
        assert len(concepts_calls) == 1
        concepts_args = concepts_calls[0][0][1]
        assert "--overlap-threshold" in concepts_args
        assert "0.6" in concepts_args

    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_no_dedup_forwarded_to_concepts(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        tickets_dir: Path,
    ) -> None:
        """--no-dedup should be forwarded to concepts stage."""
        from orchestrate_edge_pipeline import main

        mock_run_stage.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK]", stderr=""
        )
        mock_review_loop.return_value = ReviewLoopResult(passed=[], rejected=[], downgraded=[])

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--tickets-dir",
                str(tickets_dir),
                "--no-dedup",
                "--output-dir",
                str(output_dir),
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        concepts_calls = [c for c in mock_run_stage.call_args_list if c[0][0] == "concepts"]
        assert len(concepts_calls) == 1
        concepts_args = concepts_calls[0][0][1]
        assert "--no-dedup" in concepts_args

    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_overlap_threshold_not_forwarded_when_none(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        tickets_dir: Path,
    ) -> None:
        """When --overlap-threshold not specified, don't forward."""
        from orchestrate_edge_pipeline import main

        mock_run_stage.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK]", stderr=""
        )
        mock_review_loop.return_value = ReviewLoopResult(passed=[], rejected=[], downgraded=[])

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--tickets-dir",
                str(tickets_dir),
                "--output-dir",
                str(output_dir),
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        concepts_calls = [c for c in mock_run_stage.call_args_list if c[0][0] == "concepts"]
        assert len(concepts_calls) == 1
        concepts_args = concepts_calls[0][0][1]
        assert "--overlap-threshold" not in concepts_args

    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_no_dedup_not_forwarded_by_default(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        tickets_dir: Path,
    ) -> None:
        """When --no-dedup not specified, don't forward."""
        from orchestrate_edge_pipeline import main

        mock_run_stage.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK]", stderr=""
        )
        mock_review_loop.return_value = ReviewLoopResult(passed=[], rejected=[], downgraded=[])

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--tickets-dir",
                str(tickets_dir),
                "--output-dir",
                str(output_dir),
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        concepts_calls = [c for c in mock_run_stage.call_args_list if c[0][0] == "concepts"]
        assert len(concepts_calls) == 1
        concepts_args = concepts_calls[0][0][1]
        assert "--no-dedup" not in concepts_args


# ---------------------------------------------------------------------------
# --as-of forwarding tests
# ---------------------------------------------------------------------------
class TestAsOfForwarding:
    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_as_of_forwarded_to_hints_stage(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        tickets_dir: Path,
    ) -> None:
        """--as-of is forwarded to the hints stage."""
        from orchestrate_edge_pipeline import main

        mock_run_stage.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK]", stderr=""
        )
        mock_review_loop.return_value = ReviewLoopResult(passed=[], rejected=[], downgraded=[])

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--tickets-dir",
                str(tickets_dir),
                "--as-of",
                "2026-02-28",
                "--output-dir",
                str(output_dir),
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        hints_calls = [c for c in mock_run_stage.call_args_list if c[0][0] == "hints"]
        assert len(hints_calls) == 1
        hints_args = hints_calls[0][0][1]
        assert "--as-of" in hints_args
        assert "2026-02-28" in hints_args

    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_as_of_not_forwarded_when_absent(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        tickets_dir: Path,
    ) -> None:
        """--as-of should not appear in hints args when not specified."""
        from orchestrate_edge_pipeline import main

        mock_run_stage.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK]", stderr=""
        )
        mock_review_loop.return_value = ReviewLoopResult(passed=[], rejected=[], downgraded=[])

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--tickets-dir",
                str(tickets_dir),
                "--output-dir",
                str(output_dir),
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        hints_calls = [c for c in mock_run_stage.call_args_list if c[0][0] == "hints"]
        assert len(hints_calls) == 1
        hints_args = hints_calls[0][0][1]
        assert "--as-of" not in hints_args


# ---------------------------------------------------------------------------
# LLM ideas file threading tests
# ---------------------------------------------------------------------------
class TestLLMIdeasFileThreading:
    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_orchestrator_threads_llm_ideas_file(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        tickets_dir: Path,
    ) -> None:
        """--llm-ideas-file is forwarded to the hints stage."""
        from orchestrate_edge_pipeline import main

        llm_file = tmp_path / "llm_hints.yaml"
        llm_file.write_text("- title: Test hint\n  observation: obs\n")

        mock_run_stage.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK]", stderr=""
        )
        mock_review_loop.return_value = ReviewLoopResult(passed=[], rejected=[], downgraded=[])

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--tickets-dir",
                str(tickets_dir),
                "--llm-ideas-file",
                str(llm_file),
                "--output-dir",
                str(output_dir),
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        hints_calls = [c for c in mock_run_stage.call_args_list if c[0][0] == "hints"]
        assert len(hints_calls) == 1
        hints_args = hints_calls[0][0][1]
        assert "--llm-ideas-file" in hints_args
        assert str(llm_file.resolve()) in hints_args

    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_orchestrator_threads_promote_hints(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        tickets_dir: Path,
    ) -> None:
        """--promote-hints is forwarded to the concepts stage."""
        from orchestrate_edge_pipeline import main

        mock_run_stage.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK]", stderr=""
        )
        mock_review_loop.return_value = ReviewLoopResult(passed=[], rejected=[], downgraded=[])

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--tickets-dir",
                str(tickets_dir),
                "--promote-hints",
                "--output-dir",
                str(output_dir),
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        concepts_calls = [c for c in mock_run_stage.call_args_list if c[0][0] == "concepts"]
        assert len(concepts_calls) == 1
        concepts_args = concepts_calls[0][0][1]
        assert "--promote-hints" in concepts_args

    @patch("orchestrate_edge_pipeline.run_stage")
    @patch("orchestrate_edge_pipeline.run_review_loop")
    def test_orchestrator_llm_ideas_file_absent(
        self,
        mock_review_loop: MagicMock,
        mock_run_stage: MagicMock,
        tmp_path: Path,
        tickets_dir: Path,
    ) -> None:
        """When --llm-ideas-file is not specified, hints args should not contain it."""
        from orchestrate_edge_pipeline import main

        mock_run_stage.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[OK]", stderr=""
        )
        mock_review_loop.return_value = ReviewLoopResult(passed=[], rejected=[], downgraded=[])

        output_dir = tmp_path / "output"
        with patch(
            "sys.argv",
            [
                "orchestrate_edge_pipeline.py",
                "--tickets-dir",
                str(tickets_dir),
                "--output-dir",
                str(output_dir),
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        hints_calls = [c for c in mock_run_stage.call_args_list if c[0][0] == "hints"]
        assert len(hints_calls) == 1
        hints_args = hints_calls[0][0][1]
        assert "--llm-ideas-file" not in hints_args
