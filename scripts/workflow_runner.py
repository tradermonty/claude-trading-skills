"""
TraderMonty local workflow runner.

Provides a lightweight CLI to inspect, validate, start, and check status of
workflow runs WITHOUT executing any trades or automating skill invocations.

This tool is a decision-support aid, not an execution engine.  It:
  - Reads workflow manifests from workflows/*.yaml
  - Creates and persists WorkflowRun artifacts in state/workflow-runs/
  - Shows required inputs and checks for missing upstream artifacts
  - Marks decision gates so the user knows where to pause
  - Never executes any broker, API, or skill code

Usage
-----
    python scripts/workflow_runner.py list
    python scripts/workflow_runner.py validate market-regime-daily
    python scripts/workflow_runner.py start market-regime-daily [--operator "Name"]
    python scripts/workflow_runner.py status <run_id>
    python scripts/workflow_runner.py steps <run_id>
    python scripts/workflow_runner.py inspect <run_id>
    python scripts/workflow_runner.py complete-step <run_id> <step_number> [--answer "..."]
    python scripts/workflow_runner.py record-artifact <run_id> <artifact_id> [--file <path>] [--hash <sha256>] [--kind input|output]
    python scripts/workflow_runner.py approve-review <run_id> [--reviewer "..."] [--notes "..."]
    python scripts/workflow_runner.py abandon <run_id> [--reason "..."]

Manual review gate
------------------
When all steps of a workflow run are completed AND manual_review_required=True, the run
transitions to AWAITING_REVIEW — NOT to COMPLETED.  The run is finalised (COMPLETED) only
after an explicit `approve-review` call, which records the reviewer identity, timestamp,
and any review notes.  This enforces that no workflow output can be promoted without a
traceable human sign-off.

Decision gate enforcement
-------------------------
Steps marked `decision_gate: true` in the workflow manifest REQUIRE an --answer argument.
The `complete-step` command will return exit code 1 and refuse to advance the run until
the reviewer's decision is recorded.

Workflow reproducibility (Phase 7)
-----------------------------------
Each WorkflowRun artifact captures a complete provenance snapshot:
  - workflow_version:          manifest version at run-start time
  - skill_versions:            {skill_id: version} snapshot from skills-index.yaml
  - artifact_schema_versions:  {artifact_type: schema_version} snapshot
  - input_artifact_hashes:     SHA-256 of input artifacts (via record-artifact --kind input)
  - output_artifact_hashes:    SHA-256 of output artifacts (via record-artifact --kind output)
  - run_timestamp:             ISO-8601 UTC when the run was created
  - operator:                  who started the run (--operator flag on start)
  - reviewer / reviewed_at:    who approved the run (set by approve-review)

Use `inspect <run_id>` to display the full provenance report for a run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# Allow running from repo root or scripts/
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from schemas.artifacts import (  # noqa: E402
    ManualReviewStatus,
    ReviewerRole,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStepRecord,
)

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    from audit_log import AuditLog, AuditEventType  # noqa: E402
    _AUDIT_LOG: AuditLog | None = AuditLog(REPO_ROOT / "state" / "audit-log")
except ImportError:
    _AUDIT_LOG = None
    AuditEventType = None  # type: ignore[assignment,misc]

WORKFLOWS_DIR = REPO_ROOT / "workflows"
RUNS_DIR = REPO_ROOT / "state" / "workflow-runs"
SKILLS_INDEX = REPO_ROOT / "skills-index.yaml"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_workflows() -> dict[str, dict]:
    """Return {workflow_id: manifest_dict} for all *.yaml files in workflows/."""
    result = {}
    for path in sorted(WORKFLOWS_DIR.glob("*.yaml")):
        try:
            manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
            wf_id = manifest.get("id", path.stem)
            result[wf_id] = manifest
        except Exception as exc:  # noqa: BLE001
            print(f"  [WARN] Could not parse {path.name}: {exc}", file=sys.stderr)
    return result


def _load_skills_index() -> set[str]:
    """Return set of skill IDs from skills-index.yaml."""
    try:
        data = yaml.safe_load(SKILLS_INDEX.read_text(encoding="utf-8"))
        return {s["id"] for s in data.get("skills", [])}
    except Exception:  # noqa: BLE001
        return set()


def _load_run(run_id: str) -> WorkflowRun | None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / f"{run_id}.json"
    if not path.exists():
        # Try prefix match
        matches = list(RUNS_DIR.glob(f"{run_id}*.json"))
        if not matches:
            return None
        path = matches[0]
    try:
        return WorkflowRun.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Could not load run {run_id}: {exc}", file=sys.stderr)
        return None


def _save_run(run: WorkflowRun) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / f"{run.run_id}.json"
    path.write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def _sha256_file(path: Path) -> str:
    """Return SHA-256 hex digest of a file, or empty string if unreadable."""
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def _get_skill_versions(required_skills: list[str]) -> dict[str, str]:
    """Return {skill_id: version} for the given skill IDs from skills-index.yaml.

    Skills not found in the index get version "unknown".
    """
    try:
        data = yaml.safe_load(SKILLS_INDEX.read_text(encoding="utf-8"))
        index = {s["id"]: s.get("version", "unknown") for s in data.get("skills", [])}
    except Exception:  # noqa: BLE001
        index = {}
    return {skill_id: index.get(skill_id, "unknown") for skill_id in required_skills}


def _get_artifact_schema_versions() -> dict[str, str]:
    """Return {artifact_type: schema_version} for all known artifact types.

    Introspects imported artifact classes that define ARTIFACT_TYPE and schema_version.
    """
    import schemas.artifacts as _art_module

    result: dict[str, str] = {}
    for name in _art_module.__all__:
        cls = getattr(_art_module, name, None)
        if cls is None or not isinstance(cls, type):
            continue
        art_type = getattr(cls, "ARTIFACT_TYPE", None)
        if art_type is None:
            continue
        # Get the default schema_version from the model's field definition
        schema_ver = "unknown"
        fields = getattr(cls, "model_fields", {})
        sv_field = fields.get("schema_version")
        if sv_field is not None and sv_field.default is not None:
            schema_ver = str(sv_field.default)
        result[art_type] = schema_ver
    return result


def _validate_manifest(manifest: dict, known_skills: set[str]) -> list[str]:
    """Return list of error strings; empty = valid."""
    errors = []
    wf_id = manifest.get("id", "?")

    for skill in manifest.get("required_skills", []):
        if known_skills and skill not in known_skills:
            errors.append(f"WF: required skill '{skill}' not in skills-index.yaml")

    for skill in manifest.get("optional_skills", []):
        if known_skills and skill not in known_skills:
            errors.append(f"WF: optional skill '{skill}' not in skills-index.yaml")

    # Check decision gates have questions
    for step in manifest.get("steps", []):
        if step.get("decision_gate") and not step.get("decision_question"):
            errors.append(
                f"Step {step.get('step')}: decision_gate=true but no decision_question"
            )

    # Check artifacts produced_by_step references valid steps
    step_numbers = {s["step"] for s in manifest.get("steps", [])}
    for art in manifest.get("artifacts", []):
        pbs = art.get("produced_by_step")
        if pbs and pbs not in step_numbers:
            errors.append(
                f"Artifact '{art.get('id')}' references step {pbs} which doesn't exist"
            )

    # Check no execution language (best-effort)
    for field in ["when_to_run", "when_not_to_run"]:
        text = manifest.get(field, "")
        forbidden = ["place order", "execute order", "buy now", "sell now", "submit order"]
        for phrase in forbidden:
            if phrase in text.lower():
                errors.append(f"Field '{field}' contains forbidden execution language: '{phrase}'")

    # Check manual_review is present
    if not manifest.get("manual_review"):
        errors.append(f"Workflow '{wf_id}' has no manual_review checklist")

    return errors


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:
    workflows = _load_workflows()
    if not workflows:
        print("No workflow manifests found in workflows/")
        return 1

    print(f"{'ID':<35} {'Cadence':<12} {'~Min':<6} {'API':<20} Difficulty")
    print("-" * 90)
    for wf_id, m in sorted(workflows.items()):
        print(
            f"{wf_id:<35} {m.get('cadence','?'):<12} "
            f"{str(m.get('estimated_minutes','?')):<6} "
            f"{m.get('api_profile','?'):<20} "
            f"{m.get('difficulty','?')}"
        )
    print(f"\nTotal: {len(workflows)} workflow(s)")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    workflows = _load_workflows()
    known_skills = _load_skills_index()

    targets = [args.workflow_id] if args.workflow_id else list(workflows.keys())
    total_errors = 0

    for wf_id in targets:
        if wf_id not in workflows:
            print(f"[ERROR] Workflow '{wf_id}' not found")
            total_errors += 1
            continue

        manifest = workflows[wf_id]
        errors = _validate_manifest(manifest, known_skills)

        if errors:
            print(f"[FAIL] {wf_id}")
            for e in errors:
                print(f"       {e}")
            total_errors += len(errors)
        else:
            print(f"[OK]   {wf_id}")

    if total_errors:
        print(f"\n{total_errors} validation error(s)")
        return 1
    else:
        print("\nAll workflows valid.")
        return 0


def cmd_start(args: argparse.Namespace) -> int:
    workflows = _load_workflows()
    wf_id = args.workflow_id

    if wf_id not in workflows:
        print(f"[ERROR] Workflow '{wf_id}' not found.")
        print(f"Available: {', '.join(sorted(workflows))}")
        return 1

    manifest = workflows[wf_id]

    # Build step records
    steps = []
    for s in manifest.get("steps", []):
        steps.append(
            WorkflowStepRecord(
                step_number=s["step"],
                name=s.get("name", f"Step {s['step']}"),
                skill_id=s.get("skill", "unknown"),
                status="SKIPPED" if s.get("optional") and not args.include_optional else "PENDING",
                decision_gate_question=s.get("decision_question") if s.get("decision_gate") else None,
            )
        )

    # Collect provenance snapshot at start time
    all_skill_ids = list({
        s.get("skill", "unknown")
        for s in manifest.get("steps", [])
        if s.get("skill", "unknown") != "unknown"
    })
    skill_vers = _get_skill_versions(all_skill_ids)
    schema_vers = _get_artifact_schema_versions()

    now_ts = datetime.now(timezone.utc).isoformat()

    author = getattr(args, "author", None)
    run = WorkflowRun(
        skill_id="workflow-runner",
        artifact_type="workflow_run",
        workflow_id=wf_id,
        workflow_display_name=manifest.get("display_name", wf_id),
        workflow_version=manifest.get("version"),
        operator=getattr(args, "operator", None),
        author_id=author,
        run_timestamp=now_ts,
        started_at=now_ts,
        status=WorkflowStatus.STARTED,
        estimated_minutes=manifest.get("estimated_minutes"),
        steps=steps,
        skill_versions=skill_vers,
        artifact_schema_versions=schema_vers,
        data_sources_used=[],
    )

    path = _save_run(run)

    if _AUDIT_LOG is not None:
        _AUDIT_LOG.append(
            AuditEventType.WORKFLOW_STARTED,
            actor=run.operator or run.author_id or "unspecified",
            run_id=run.run_id,
            details={"workflow_id": wf_id},
        )

    print(f"\nStarted workflow run: {run.run_id}")
    print(f"Workflow:   {run.workflow_display_name}")
    try:
        saved_display = path.relative_to(REPO_ROOT)
    except ValueError:
        saved_display = path
    print(f"Saved to:   {saved_display}")
    print(f"\n{'When to run:'}")
    print(f"  {manifest.get('when_to_run', '').strip()}")
    print(f"\n{'When NOT to run:'}")
    print(f"  {manifest.get('when_not_to_run', '').strip()}")

    print(f"\nSteps ({len(steps)} total):")
    for step in steps:
        gate_marker = " [DECISION GATE]" if step.decision_gate_question else ""
        optional_marker = " (optional)" if step.status == "SKIPPED" else ""
        print(f"  {step.step_number}. {step.name} — skill: {step.skill_id}{gate_marker}{optional_marker}")

    print(f"\nRequired inputs:")
    for skill_id in manifest.get("required_skills", []):
        print(f"  - {skill_id}")

    if manifest.get("optional_skills"):
        print(f"\nOptional inputs:")
        for skill_id in manifest.get("optional_skills", []):
            print(f"  - {skill_id}")

    if manifest.get("prerequisite_workflows"):
        print(f"\nPrerequisite workflows (informational — not enforced):")
        for pw in manifest.get("prerequisite_workflows", []):
            print(f"  - {pw.get('id')} → produces: {pw.get('artifact')}")

    print(f"\nManual review checklist (complete before journaling):")
    for item in manifest.get("manual_review", []):
        print(f"  [ ] {item}")

    print(f"\nRun 'python scripts/workflow_runner.py steps {run.run_id}' to see step details.")
    print(f"Run 'python scripts/workflow_runner.py complete-step {run.run_id} 1' to mark step 1 done.")

    _print_disclaimer()
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    run = _load_run(args.run_id)
    if run is None:
        print(f"[ERROR] Run '{args.run_id}' not found in {RUNS_DIR}/")
        return 1

    completed = sum(1 for s in run.steps if s.status == "DONE")
    total = sum(1 for s in run.steps if s.status != "SKIPPED")

    print(f"\nWorkflow Run: {run.run_id}")
    print(f"Workflow:     {run.workflow_display_name or run.workflow_id}")
    print(f"Status:       {run.status.value}")
    print(f"Review:       {run.manual_review_status.value}"
          + (f"  (by {run.reviewer})" if run.reviewer else ""))
    print(f"Started:      {run.started_at}")
    print(f"Completed:    {run.completed_at or '—'}")
    print(f"Progress:     {completed}/{total} steps done")

    if run.artifact_ids:
        print(f"\nArtifacts produced: {len(run.artifact_ids)}")
        for aid in run.artifact_ids:
            print(f"  {aid}")

    if run.decision_gate_log:
        print(f"\nDecision gate log:")
        for entry in run.decision_gate_log:
            print(f"  Step {entry.get('step')}: {entry.get('answer', '—')[:80]}")

    return 0


def cmd_steps(args: argparse.Namespace) -> int:
    run = _load_run(args.run_id)
    if run is None:
        print(f"[ERROR] Run '{args.run_id}' not found.")
        return 1

    print(f"\nSteps for run {run.run_id} ({run.workflow_display_name or run.workflow_id}):\n")
    for step in run.steps:
        icon = {"PENDING": "○", "RUNNING": "▶", "DONE": "✓", "SKIPPED": "—", "FAILED": "✗"}.get(
            step.status, "?"
        )
        gate_str = f"\n    → DECISION: {step.decision_gate_question}" if step.decision_gate_question else ""
        answer_str = (
            f"\n    → ANSWER: {step.decision_gate_answer}" if step.decision_gate_answer else ""
        )
        print(
            f"  {icon} Step {step.step_number}: {step.name}\n"
            f"    Skill: {step.skill_id}  |  Status: {step.status}"
            f"{gate_str}{answer_str}"
        )
    return 0


def cmd_complete_step(args: argparse.Namespace) -> int:
    run = _load_run(args.run_id)
    if run is None:
        print(f"[ERROR] Run '{args.run_id}' not found.")
        return 1

    step_num = int(args.step_number)
    step = next((s for s in run.steps if s.step_number == step_num), None)
    if step is None:
        print(f"[ERROR] Step {step_num} not found in run {args.run_id}.")
        return 1

    # Enforce: decision gate steps REQUIRE an answer before they can be completed.
    if step.decision_gate_question and not args.answer:
        print(
            f"[BLOCKED] Step {step_num} is a decision gate and requires an answer.\n"
            f"          Question: {step.decision_gate_question}\n"
            f"          Provide your answer with --answer \"<your decision>\""
        )
        return 1

    now = datetime.now(timezone.utc).isoformat()
    step.status = "DONE"
    step.completed_at = now
    if step.started_at is None:
        step.started_at = now

    if args.answer and step.decision_gate_question:
        step.decision_gate_answer = args.answer
        run.decision_gate_log.append(
            {"step": str(step_num), "question": step.decision_gate_question, "answer": args.answer}
        )
        if _AUDIT_LOG is not None:
            _AUDIT_LOG.append(
                AuditEventType.DECISION_GATE_ANSWERED,
                actor=run.operator or run.author_id or "unspecified",
                run_id=run.run_id,
                details={"step": step_num, "question": step.decision_gate_question, "answer": args.answer},
            )

    # Update run status
    pending = [s for s in run.steps if s.status in ("PENDING", "RUNNING")]
    if not pending:
        # All steps done — transition to AWAITING_REVIEW if review required.
        # Only approve-review can set status to COMPLETED.
        if run.manual_review_required:
            run.status = WorkflowStatus.AWAITING_REVIEW
            run.manual_review_status = ManualReviewStatus.PENDING
        else:
            run.status = WorkflowStatus.COMPLETED
            run.completed_at = now
    else:
        run.status = WorkflowStatus.IN_PROGRESS

    path = _save_run(run)

    if _AUDIT_LOG is not None:
        _AUDIT_LOG.append(
            AuditEventType.STEP_COMPLETED,
            actor=run.operator or run.author_id or "unspecified",
            run_id=run.run_id,
            details={"step": step_num, "step_name": step.name},
        )

    print(f"[OK] Step {step_num} marked DONE for run {args.run_id}")
    if run.status == WorkflowStatus.AWAITING_REVIEW:
        print(
            "\n⚠  All steps complete — workflow is now AWAITING_REVIEW.\n"
            "   Manual review required before this run can be finalised.\n"
            f"   Run: python scripts/workflow_runner.py approve-review {run.run_id} "
            f"--reviewer \"<name>\" --notes \"<notes>\"\n"
            "   to approve and mark the run COMPLETED."
        )
    elif run.status == WorkflowStatus.COMPLETED:
        print("     All steps complete — workflow run COMPLETED.")
        print("     Remember to journal this run to trader-memory-core.")
    return 0


def cmd_approve_review(args: argparse.Namespace) -> int:
    """Approve the manual review for a completed workflow run, finalising it."""
    run = _load_run(args.run_id)
    if run is None:
        print(f"[ERROR] Run '{args.run_id}' not found.")
        return 1

    if run.status == WorkflowStatus.COMPLETED:
        print(f"[INFO] Run {args.run_id} is already COMPLETED (review was previously approved).")
        return 0

    if run.status != WorkflowStatus.AWAITING_REVIEW:
        print(
            f"[ERROR] Run {args.run_id} is in status '{run.status.value}', "
            f"not AWAITING_REVIEW.\n"
            f"        Only runs in AWAITING_REVIEW status can be approved.\n"
            f"        Complete all steps first with: "
            f"python scripts/workflow_runner.py complete-step {args.run_id} <step>"
        )
        return 1

    # Check all decision gates have been answered
    unanswered = [
        s for s in run.steps
        if s.decision_gate_question and not s.decision_gate_answer
    ]
    if unanswered:
        print(
            f"[BLOCKED] Cannot approve: {len(unanswered)} decision gate(s) have no answer:\n"
            + "\n".join(
                f"  Step {s.step_number}: {s.decision_gate_question}" for s in unanswered
            )
        )
        return 1

    reviewer = args.reviewer or "unspecified"

    # Self-review guard
    author = run.author_id or run.operator or ""
    if (
        author
        and reviewer not in ("unspecified", "")
        and author == reviewer
    ):
        print(
            f"[BLOCKED] Self-review is not permitted: operator/author '{author}' "
            f"cannot approve their own run.\n"
            f"          Use a different reviewer identity."
        )
        return 1

    # Resolve reviewer_role
    reviewer_role_raw = getattr(args, "reviewer_role", None) or "REVIEWER"
    try:
        reviewer_role = ReviewerRole(reviewer_role_raw.upper())
    except ValueError:
        print(
            f"[ERROR] Unknown reviewer_role '{reviewer_role_raw}'. "
            f"Valid values: {', '.join(r.value for r in ReviewerRole)}"
        )
        return 1

    now = datetime.now(timezone.utc).isoformat()
    run.status = WorkflowStatus.COMPLETED
    run.completed_at = now
    run.manual_review_status = ManualReviewStatus.APPROVED
    run.reviewer = reviewer
    run.reviewer_role = reviewer_role
    run.reviewed_at = now
    run.review_notes = args.notes or ""

    _save_run(run)

    if _AUDIT_LOG is not None:
        _AUDIT_LOG.append(
            AuditEventType.REVIEW_APPROVED,
            actor=reviewer,
            run_id=run.run_id,
            details={"reviewer_role": reviewer_role.value, "notes": run.review_notes},
        )

    print(f"[APPROVED] Run {args.run_id} — manual review complete.")
    print(f"           Status:   COMPLETED")
    print(f"           Reviewer: {run.reviewer} ({reviewer_role.value})")
    if run.review_notes:
        print(f"           Notes:    {run.review_notes}")
    print("\nRemember to journal this run to trader-memory-core.")
    _print_disclaimer()
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    """Print full provenance report for a workflow run."""
    run = _load_run(args.run_id)
    if run is None:
        print(f"[ERROR] Run '{args.run_id}' not found in {RUNS_DIR}/")
        return 1

    print("=" * 70)
    print("WORKFLOW RUN PROVENANCE REPORT")
    print("=" * 70)
    print(f"  Run ID:             {run.run_id}")
    print(f"  Workflow:           {run.workflow_display_name or run.workflow_id}")
    print(f"  Workflow ID:        {run.workflow_id}")
    print(f"  Workflow Version:   {run.workflow_version or '—'}")
    print(f"  Run Timestamp:      {run.run_timestamp}")
    print(f"  Started At:         {run.started_at}")
    print(f"  Completed At:       {run.completed_at or '—'}")
    print(f"  Status:             {run.status.value}")
    print(f"  Operator:           {run.operator or '—'}")
    print()

    print("REVIEW PROVENANCE")
    print("-" * 40)
    print(f"  Manual Review:      {run.manual_review_status.value}")
    print(f"  Reviewer:           {run.reviewer or '—'}")
    print(f"  Reviewed At:        {run.reviewed_at or '—'}")
    print(f"  Review Notes:       {run.review_notes or '—'}")
    print()

    print("SKILL VERSIONS (at run-start)")
    print("-" * 40)
    if run.skill_versions:
        for sid, ver in sorted(run.skill_versions.items()):
            print(f"  {sid:<40} {ver}")
    else:
        print("  (none recorded)")
    print()

    print("ARTIFACT SCHEMA VERSIONS (at run-start)")
    print("-" * 40)
    if run.artifact_schema_versions:
        for art_type, ver in sorted(run.artifact_schema_versions.items()):
            print(f"  {art_type:<40} {ver}")
    else:
        print("  (none recorded)")
    print()

    print("INPUT ARTIFACT HASHES")
    print("-" * 40)
    if run.input_artifact_hashes:
        for art_id, sha in sorted(run.input_artifact_hashes.items()):
            print(f"  {art_id[:40]:<42}  sha256:{sha[:16]}…")
    else:
        print("  (none recorded)")
    print()

    print("OUTPUT ARTIFACT HASHES")
    print("-" * 40)
    if run.output_artifact_hashes:
        for art_id, sha in sorted(run.output_artifact_hashes.items()):
            print(f"  {art_id[:40]:<42}  sha256:{sha[:16]}…")
    else:
        print("  (none recorded)")
    print()

    print("STEP AUDIT TRAIL")
    print("-" * 40)
    for step in run.steps:
        icon = {"PENDING": "○", "RUNNING": "▶", "DONE": "✓", "SKIPPED": "—", "FAILED": "✗"}.get(
            step.status, "?"
        )
        print(f"  {icon} Step {step.step_number}: {step.name} ({step.skill_id})")
        if step.started_at:
            print(f"      Started:   {step.started_at}")
        if step.completed_at:
            print(f"      Completed: {step.completed_at}")
        if step.decision_gate_question:
            print(f"      Gate:      {step.decision_gate_question}")
            print(f"      Answer:    {step.decision_gate_answer or '(unanswered)'}")
        if step.input_artifact_ids:
            print(f"      Inputs:    {', '.join(step.input_artifact_ids)}")
        if step.output_artifact_hashes:
            for aid, sha in step.output_artifact_hashes.items():
                print(f"      Output:    {aid}  sha256:{sha[:16]}…")
    print()

    print("DECISION GATE LOG")
    print("-" * 40)
    if run.decision_gate_log:
        for entry in run.decision_gate_log:
            print(f"  Step {entry.get('step')}: Q: {entry.get('question','')[:60]}")
            print(f"          A: {entry.get('answer','')[:80]}")
    else:
        print("  (no decision gates answered yet)")
    print("=" * 70)
    return 0


def cmd_record_artifact(args: argparse.Namespace) -> int:
    """Record an artifact hash in the workflow run for reproducibility tracking."""
    run = _load_run(args.run_id)
    if run is None:
        print(f"[ERROR] Run '{args.run_id}' not found.")
        return 1

    artifact_id = args.artifact_id
    kind = (args.kind or "output").lower()

    # Determine the SHA-256 hash
    if args.hash:
        sha = args.hash
    elif args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"[ERROR] File not found: {args.file}")
            return 1
        sha = _sha256_file(path)
        if not sha:
            print(f"[ERROR] Could not read file: {args.file}")
            return 1
    else:
        print("[ERROR] Must provide either --hash <sha256> or --file <path>")
        return 1

    if kind == "input":
        run.input_artifact_hashes[artifact_id] = sha
    else:
        run.output_artifact_hashes[artifact_id] = sha
        if artifact_id not in run.artifact_ids:
            run.artifact_ids.append(artifact_id)

    # Also record on the active step if step_number is given
    if args.step_number is not None:
        step_num = int(args.step_number)
        step = next((s for s in run.steps if s.step_number == step_num), None)
        if step is not None and kind == "output":
            step.output_artifact_hashes[artifact_id] = sha
        elif step is not None and kind == "input":
            if artifact_id not in step.input_artifact_ids:
                step.input_artifact_ids.append(artifact_id)

    _save_run(run)

    if _AUDIT_LOG is not None:
        _AUDIT_LOG.append(
            AuditEventType.ARTIFACT_RECORDED,
            actor=run.operator or run.author_id or "unspecified",
            run_id=run.run_id,
            details={"artifact_id": artifact_id, "kind": kind, "sha256": sha[:16]},
        )

    print(f"[OK] Recorded {kind} artifact '{artifact_id}' sha256:{sha[:16]}… on run {run.run_id}")
    return 0


def cmd_abandon(args: argparse.Namespace) -> int:
    run = _load_run(args.run_id)
    if run is None:
        print(f"[ERROR] Run '{args.run_id}' not found.")
        return 1

    run.status = WorkflowStatus.ABANDONED
    run.abort_reason = args.reason or "User abandoned"
    run.completed_at = datetime.now(timezone.utc).isoformat()

    _save_run(run)
    print(f"Run {args.run_id} marked ABANDONED.")
    return 0


def cmd_audit_log(args: argparse.Namespace) -> int:
    """Display recent audit log entries and verify the hash chain."""
    if _AUDIT_LOG is None:
        print("[ERROR] audit_log module is not available.")
        return 1

    entries = _AUDIT_LOG.entries()
    limit = getattr(args, "last", 20) or 20
    display = entries[-limit:] if len(entries) > limit else entries

    if not display:
        print("Audit log is empty.")
    else:
        print(f"\nAudit Log — last {len(display)} of {len(entries)} entries")
        print("-" * 70)
        for entry in display:
            ts = entry.get("timestamp", "?")[:19].replace("T", " ")
            event = entry.get("event_type", "?")
            actor = entry.get("actor", "?")
            run_id = entry.get("run_id", "")
            run_str = f"  run={run_id}" if run_id else ""
            print(f"  {ts}  {event:<35} actor={actor}{run_str}")

    # Verify chain
    errors = _AUDIT_LOG.verify_chain()
    print()
    if errors:
        print(f"[CHAIN INVALID] {len(errors)} error(s):")
        for err in errors:
            print(f"  {err}")
        return 1
    else:
        print(f"[CHAIN VALID] {len(entries)} entries, hash chain intact.")
    return 0


def _print_disclaimer() -> None:
    print(
        "\n⚠  IMPORTANT: This tool is for decision-support only. It does NOT execute trades, "
        "place orders, or automate skill calls. All actions require manual execution and review."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TraderMonty workflow runner — decision-support only, no execution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all available workflows")

    p_val = sub.add_parser("validate", help="Validate workflow manifest(s)")
    p_val.add_argument("workflow_id", nargs="?", help="Workflow ID to validate (omit for all)")

    p_start = sub.add_parser("start", help="Start a new workflow run")
    p_start.add_argument("workflow_id", help="Workflow ID to start")
    p_start.add_argument(
        "--include-optional",
        action="store_true",
        help="Include optional steps in the run (default: mark them SKIPPED)",
    )
    p_start.add_argument(
        "--operator",
        help="Name or identifier of the person starting this run (recorded for audit trail)",
    )
    p_start.add_argument(
        "--author",
        help="ID of the artifact author; used to prevent self-review (defaults to --operator if omitted)",
    )

    p_status = sub.add_parser("status", help="Show status of a workflow run")
    p_status.add_argument("run_id", help="Run ID (or prefix)")

    p_steps = sub.add_parser("steps", help="Show all steps for a run")
    p_steps.add_argument("run_id", help="Run ID (or prefix)")

    p_inspect = sub.add_parser("inspect", help="Show full provenance report for a run")
    p_inspect.add_argument("run_id", help="Run ID (or prefix)")

    p_record = sub.add_parser("record-artifact", help="Record an artifact hash for reproducibility")
    p_record.add_argument("run_id", help="Run ID")
    p_record.add_argument("artifact_id", help="Artifact ID to record")
    p_record.add_argument(
        "--hash",
        dest="hash",
        help="SHA-256 hex digest of the artifact",
    )
    p_record.add_argument(
        "--file",
        help="Path to the artifact file (SHA-256 computed automatically)",
    )
    p_record.add_argument(
        "--kind",
        choices=["input", "output"],
        default="output",
        help="Whether this is an input or output artifact (default: output)",
    )
    p_record.add_argument(
        "--step",
        dest="step_number",
        type=int,
        default=None,
        help="Step number to associate this artifact with (optional)",
    )

    p_complete = sub.add_parser("complete-step", help="Mark a step as done")
    p_complete.add_argument("run_id", help="Run ID")
    p_complete.add_argument("step_number", help="Step number to mark done")
    p_complete.add_argument("--answer", help="Decision gate answer (if applicable)")

    p_approve = sub.add_parser(
        "approve-review",
        help="Approve the manual review for a run, finalising it as COMPLETED",
    )
    p_approve.add_argument("run_id", help="Run ID to approve")
    p_approve.add_argument(
        "--reviewer",
        help="Name or identifier of the reviewer (defaults to 'unspecified')",
    )
    p_approve.add_argument(
        "--notes",
        help="Review notes or rationale (optional)",
    )
    p_approve.add_argument(
        "--reviewer-role",
        dest="reviewer_role",
        default="REVIEWER",
        help="Role of the reviewer (RESEARCHER/REVIEWER/RISK_APPROVER/ADMIN; default: REVIEWER)",
    )

    p_abandon = sub.add_parser("abandon", help="Abandon a workflow run")
    p_abandon.add_argument("run_id", help="Run ID")
    p_abandon.add_argument("--reason", help="Reason for abandonment")

    p_audit = sub.add_parser("audit-log", help="Display recent audit log entries and verify chain")
    p_audit.add_argument(
        "--last",
        type=int,
        default=20,
        help="Number of recent entries to display (default: 20)",
    )

    return parser


COMMANDS = {
    "list": cmd_list,
    "validate": cmd_validate,
    "start": cmd_start,
    "status": cmd_status,
    "steps": cmd_steps,
    "inspect": cmd_inspect,
    "record-artifact": cmd_record_artifact,
    "complete-step": cmd_complete_step,
    "approve-review": cmd_approve_review,
    "abandon": cmd_abandon,
    "audit-log": cmd_audit_log,
}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    handler = COMMANDS.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
