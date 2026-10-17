"""Collect attributable GitHub evidence for the committed quality dashboard.

The generator stays offline. This explicit refresh requires read-only GitHub
access via gh; API failures abort before any output is written.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from generate_quality_dashboard import (
    DEFAULT_SNAPSHOT_PATH,
    NOT_YET_MEASURED,
    catalog_fingerprint,
    load_index,
)
from validate_skills_index import VERIFICATION_AXES


class RefreshError(ValueError):
    """Unavailable or invalid evidence; do not publish a partial refresh."""


def command(args: list[str]) -> bytes:
    try:
        result = subprocess.run(args, capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RefreshError(f"command unavailable or timed out: {args[0]}") from exc
    if result.returncode:
        # Do not reflect token-bearing environment or server response bodies.
        raise RefreshError(f"command failed: {args[0]} (exit {result.returncode})")
    return result.stdout


class GitHub:
    def __init__(self, repo: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise RefreshError("repository must be OWNER/REPO")
        self.base = f"repos/{repo}"

    def get(self, endpoint: str) -> Any:
        try:
            return json.loads(command(["gh", "api", f"{self.base}/{endpoint}"]))
        except (ValueError, UnicodeError) as exc:
            raise RefreshError("invalid GitHub JSON") from exc

    def pages(self, endpoint: str) -> list[Any]:
        try:
            pages = json.loads(
                command(["gh", "api", "--paginate", "--slurp", f"{self.base}/{endpoint}"])
            )
            if not isinstance(pages, list) or not all(isinstance(p, list) for p in pages):
                raise ValueError("expected arrays")
            return [row for page in pages for row in page]
        except (ValueError, UnicodeError) as exc:
            raise RefreshError("invalid paginated GitHub JSON") from exc

    def artifact(self, artifact_id: int) -> bytes:
        return command(["gh", "api", f"{self.base}/actions/artifacts/{artifact_id}/zip"])


def coverage_values(archive: bytes, skill_ids: set[str]) -> dict[str, float]:
    """Read one whitelisted member without extracting any archive paths."""
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            members = [m for m in zf.infolist() if m.filename == "per-skill-coverage.json"]
            if len(members) != 1 or members[0].file_size > 5_000_000:
                raise RefreshError("coverage artifact requires one bounded per-skill-coverage.json")
            data = json.loads(zf.read(members[0]))
        if data.get("schema_version") != 1 or isinstance(data.get("schema_version"), bool):
            raise RefreshError("unsupported coverage schema")
        if not isinstance(data.get("skills"), list):
            raise RefreshError("coverage skills must be an array")
        values = {}
        seen = set()
        for row in data["skills"]:
            sid, value = row["id"], row["actual"]
            if sid in seen or sid not in skill_ids | {"repo-scripts"}:
                raise RefreshError("duplicate or unknown coverage skill")
            seen.add(sid)
            if value is None:
                continue
            if (
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not math.isfinite(value)
                or not 0 <= value <= 100
            ):
                raise RefreshError("coverage must be a finite percentage")
            if sid in skill_ids:
                values[sid] = value
        return values
    except (ValueError, KeyError, TypeError, AttributeError, zipfile.BadZipFile) as exc:
        raise RefreshError(f"invalid coverage artifact: {exc}") from exc


def collect(root: Path, github: GitHub, measured_at: str, commit: str) -> dict[str, Any]:
    index = load_index(root)
    skills = index.get("skills", [])
    skill_ids = {s["id"] for s in skills}
    snapshot: dict[str, Any] = {
        "schema_version": 2,
        "as_of": measured_at,
        "per_skill_coverage_pct": {},
        "beta_since": {},
        "dual_axis_score_distribution": NOT_YET_MEASURED,
        "open_high_severity_issues": NOT_YET_MEASURED,
        "last_successful_ci_timestamp": NOT_YET_MEASURED,
        "executed_smoke_count": NOT_YET_MEASURED,
        "latest_successful_live_sample": NOT_YET_MEASURED,
        "drift_status": {},
        "input_provenance": {},
    }
    provenance = snapshot["input_provenance"]
    provenance["catalog"] = {
        "content_sha256": catalog_fingerprint(root),
        "commit": commit,
        "measured_at": measured_at,
        "source": "skills-index.yaml; config/ci-test-policy.yaml; examples/workflows/replay-coverage.yaml",
    }
    axes = {}
    for axis in sorted(VERIFICATION_AXES):
        axes[axis] = {
            status: sum(
                s.get("verification", {}).get(axis, "not_verified") == status
                for s in skills
                if s.get("status") == "production"
            )
            for status in ("passed", "not_verified", "not_applicable")
        }
    snapshot["production_verification_declarations"] = axes
    provenance["production_verification_declarations"] = dict(provenance["catalog"])

    issues = github.pages("issues?state=open&per_page=100")
    snapshot["open_high_severity_issues"] = sum(
        "pull_request" not in issue
        and (
            re.search(r"\[P[01]\]", issue.get("title", ""), flags=re.IGNORECASE) is not None
            or any(
                label.get("name", "").lower() in {"p0", "p1", "priority:p0", "priority:p1"}
                for label in issue.get("labels", [])
            )
        )
        for issue in issues
    )
    provenance["open_high_severity_issues"] = {
        "commit": "not applicable (live issue state)",
        "measured_at": measured_at,
        "source": f"https://github.com/{github.base.removeprefix('repos/')}/issues",
    }
    runs = github.get(
        "actions/workflows/ci.yml/runs?branch=main&event=push&status=success&per_page=1"
    )["workflow_runs"]
    if not runs:
        return snapshot
    run = runs[0]
    if (
        run.get("conclusion") != "success"
        or run.get("head_branch") != "main"
        or run.get("event") != "push"
        or not re.fullmatch(r"[0-9a-f]{40}", run.get("head_sha", ""))
    ):
        raise RefreshError("CI evidence must be a successful main push run")
    run_id = run["id"]
    ci_source = {
        "commit": run["head_sha"],
        "measured_at": run["updated_at"],
        "source": run["html_url"],
    }
    snapshot["last_successful_ci_timestamp"] = run["updated_at"]
    provenance["last_successful_ci_timestamp"] = ci_source
    artifacts = github.get(f"actions/runs/{run_id}/artifacts?per_page=100")
    # The combined report is one of at most 100 CI artifacts (one per matrix row).
    # Refuse truncation rather than silently treating later artifacts as missing.
    if artifacts["total_count"] > len(artifacts["artifacts"]):
        raise RefreshError("CI artifact list is truncated")
    candidates = [
        a
        for a in artifacts["artifacts"]
        if a["name"] == "executable-code-coverage-report" and not a.get("expired", True)
    ]
    if len(candidates) > 1:
        raise RefreshError("ambiguous coverage artifacts")
    if candidates:
        artifact = candidates[0]
        workflow_run = artifact.get("workflow_run", {})
        if workflow_run.get("id") != run_id or workflow_run.get("head_sha") != run["head_sha"]:
            raise RefreshError("coverage artifact run identity mismatch")
        snapshot["per_skill_coverage_pct"] = coverage_values(
            github.artifact(artifact["id"]), skill_ids
        )
        provenance["per_skill_coverage_pct"] = {
            **ci_source,
            "source": f"{run['html_url']}/artifacts/{artifact['id']}",
        }
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="tradermonty/claude-trading-skills")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        commit = (
            command(["git", "-C", str(args.project_root), "rev-parse", "HEAD"]).decode().strip()
        )
        measured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        snapshot = collect(args.project_root, GitHub(args.repo), measured_at, commit)
        path = args.project_root / DEFAULT_SNAPSHOT_PATH
        payload = json.dumps(snapshot, indent=2, sort_keys=True, allow_nan=False) + "\n"
        path.with_suffix(".tmp").write_text(payload, encoding="utf-8")
        path.with_suffix(".tmp").replace(path)
    except (RefreshError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
