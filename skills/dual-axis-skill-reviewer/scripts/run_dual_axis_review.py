#!/usr/bin/env python3
"""Dual-axis skill reviewer: auto checks + optional LLM score merge."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class Finding:
    severity: str
    path: str
    line: int | None
    message: str
    improvement: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Pick one random skill (skills/*/SKILL.md), run rule-based review, and optionally "
            "merge an LLM review score."
        )
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root (default: current directory)",
    )
    parser.add_argument(
        "--skill",
        help="Optional skill name (e.g. vcp-screener) or SKILL.md path",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Random seed (for reproducible skill selection)",
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Directory for markdown/json review output (default: reports)",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip running skill-level tests during review",
    )
    parser.add_argument(
        "--emit-llm-prompt",
        action="store_true",
        help="Write an LLM review request prompt file alongside the report",
    )
    parser.add_argument(
        "--llm-review-json",
        help=(
            "Path to LLM review JSON. Expected shape: "
            "{score, summary, findings:[{severity,path,line,message,improvement}]}"
        ),
    )
    parser.add_argument(
        "--auto-weight",
        type=float,
        default=0.5,
        help="Weight for auto score when LLM score is provided (default: 0.5)",
    )
    parser.add_argument(
        "--llm-weight",
        type=float,
        default=0.5,
        help="Weight for LLM score when LLM score is provided (default: 0.5)",
    )
    return parser.parse_args()


def discover_skills(project_root: Path) -> list[Path]:
    return sorted(project_root.glob("skills/*/SKILL.md"))


def pick_skill(skills: list[Path], user_value: str | None, seed: int | None) -> Path:
    if user_value:
        requested = Path(user_value)
        if requested.name == "SKILL.md" and requested.exists():
            return requested.resolve()
        if "/" in user_value or user_value.endswith(".md"):
            candidate = (Path.cwd() / requested).resolve()
            if candidate.exists():
                return candidate
        by_name = [p for p in skills if p.parent.name == user_value]
        if by_name:
            return by_name[0]
        raise ValueError(f"Skill not found: {user_value}")

    rng = random.Random(seed)
    return rng.choice(skills)


def find_line(lines: list[str], pattern: str) -> int | None:
    for idx, line in enumerate(lines, start=1):
        if re.search(pattern, line):
            return idx
    return None


def has_heading(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE) for pattern in patterns)


def parse_frontmatter(lines: list[str]) -> dict[str, str]:
    if not lines or lines[0].strip() != "---":
        return {}
    try:
        end = lines[1:].index("---\n") + 1
    except ValueError:
        return {}

    data: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def extract_bash_blocks(text: str) -> list[str]:
    blocks = re.findall(r"```bash\s*(.*?)```", text, flags=re.DOTALL)
    return [block.strip() for block in blocks if block.strip()]


def collect_output_dir_values(bash_blocks: list[str]) -> list[str]:
    values: list[str] = []
    pattern = re.compile(r"--output-dir\s+([^\s]+)")
    for block in bash_blocks:
        for cmd_line in block.splitlines():
            match = pattern.search(cmd_line)
            if match:
                values.append(match.group(1))
    return values


def run_tests(project_root: Path, skill_dir: Path) -> tuple[str, str | None, str]:
    tests_dir = skill_dir / "scripts" / "tests"
    test_files = list(tests_dir.glob("test_*.py"))
    if not tests_dir.exists() or not test_files:
        return "not_found", None, ""

    command = [
        "uv",
        "run",
        "--extra",
        "dev",
        "pytest",
        str(tests_dir),
        "-q",
    ]
    command_text = " ".join(command)

    try:
        env = dict(os.environ)
        env["UV_CACHE_DIR"] = str(project_root / ".uv-cache")
        proc = subprocess.run(
            command,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
            env=env,
        )
    except FileNotFoundError:
        return "tool_missing", command_text, "uv command not found"
    except subprocess.TimeoutExpired:
        return "timeout", command_text, "pytest timeout (>180s)"

    output = f"{proc.stdout}\n{proc.stderr}".strip()
    if proc.returncode == 0:
        return "passed", command_text, output
    return "failed", command_text, output


def normalize_severity(value: str) -> str:
    candidate = (value or "").strip().lower()
    if candidate in {"high", "medium", "low"}:
        return candidate
    return "medium"


def load_llm_review(llm_review_json: str | None, project_root: Path) -> dict | None:
    if not llm_review_json:
        return None

    path = (project_root / llm_review_json).resolve()
    if not path.exists():
        raise ValueError(f"LLM review JSON not found: {llm_review_json}")

    data = json.loads(path.read_text(encoding="utf-8"))
    score = data.get("score")
    if not isinstance(score, (int, float)):
        raise ValueError("LLM review JSON must include numeric `score`.")

    findings_raw = data.get("findings", [])
    if findings_raw is None:
        findings_raw = []
    if not isinstance(findings_raw, list):
        raise ValueError("LLM review JSON `findings` must be a list.")

    findings = []
    for raw in findings_raw:
        if not isinstance(raw, dict):
            continue
        findings.append(
            {
                "severity": normalize_severity(str(raw.get("severity", "medium"))),
                "path": str(raw.get("path", "")),
                "line": raw.get("line"),
                "message": str(raw.get("message", "")).strip(),
                "improvement": str(raw.get("improvement", "")).strip(),
            }
        )

    return {
        "provided": True,
        "source_file": str(path),
        "score": max(0, min(100, int(round(float(score))))),
        "summary": str(data.get("summary", "")).strip(),
        "findings": findings,
    }


def collect_skill_inventory(project_root: Path, skill_dir: Path) -> dict:
    def rel(items: list[Path]) -> list[str]:
        return [str(item.relative_to(project_root)) for item in sorted(items)]

    return {
        "skill_md": str((skill_dir / "SKILL.md").relative_to(project_root)),
        "scripts": rel(list((skill_dir / "scripts").glob("*.py"))),
        "tests": rel(list((skill_dir / "scripts" / "tests").glob("test_*.py"))),
        "references": rel(list((skill_dir / "references").glob("*.md"))),
    }


def build_llm_prompt(
    project_root: Path,
    skill_dir: Path,
    auto_review: dict,
) -> str:
    inventory = collect_skill_inventory(project_root, skill_dir)
    lines = [
        "# LLM Skill Review Request",
        "",
        "Please perform a deep review of the following skill, including:",
        "- SKILL.md instruction quality and consistency",
        "- helper scripts for correctness/risk",
        "- tests and coverage gaps",
        "- practical usability for operators",
        "",
        "## Skill",
        f"- Name: `{auto_review['skill_name']}`",
        f"- SKILL.md: `{inventory['skill_md']}`",
        "",
        "## Files to inspect",
        "- Scripts:",
    ]
    lines.extend([f"  - `{path}`" for path in inventory["scripts"]] or ["  - (none)"])
    lines.append("- Tests:")
    lines.extend([f"  - `{path}`" for path in inventory["tests"]] or ["  - (none)"])
    lines.append("- References:")
    lines.extend([f"  - `{path}`" for path in inventory["references"]] or ["  - (none)"])
    lines.extend(
        [
            "",
            "## Auto-axis baseline (for reference only; verify independently)",
            f"- Auto score: {auto_review['score']}/100",
            "- Auto findings:",
        ]
    )
    if auto_review["findings"]:
        for finding in auto_review["findings"]:
            lines.append(f"  - [{finding['severity']}] {finding['message']}")
    else:
        lines.append("  - none")

    lines.extend(
        [
            "",
            "## Output format (strict JSON only)",
            "```json",
            "{",
            '  "score": 0,',
            '  "summary": "one-paragraph overall assessment",',
            '  "findings": [',
            "    {",
            '      "severity": "high|medium|low",',
            '      "path": "skills/.../file.ext",',
            '      "line": 0,',
            '      "message": "problem statement",',
            '      "improvement": "concrete fix"',
            "    }",
            "  ]",
            "}",
            "```",
            "",
            "Scoring rule: 0-100. If score < 90, include concrete improvements.",
        ]
    )
    return "\n".join(lines) + "\n"


def combine_reviews(
    auto_review: dict,
    llm_review: dict | None,
    auto_weight: float,
    llm_weight: float,
) -> dict:
    if llm_review and llm_review.get("provided"):
        aw = max(0.0, auto_weight)
        lw = max(0.0, llm_weight)
        if aw + lw == 0:
            aw = 0.5
            lw = 0.5
        aw_norm = aw / (aw + lw)
        lw_norm = lw / (aw + lw)
        final_score = int(round(auto_review["score"] * aw_norm + llm_review["score"] * lw_norm))
        weights = {"auto_weight": aw_norm, "llm_weight": lw_norm}
    else:
        final_score = int(auto_review["score"])
        weights = {"auto_weight": 1.0, "llm_weight": 0.0}

    combined_findings = []
    for finding in auto_review.get("findings", []):
        combined_findings.append({**finding, "axis": "auto"})
    if llm_review and llm_review.get("provided"):
        for finding in llm_review.get("findings", []):
            combined_findings.append({**finding, "axis": "llm"})

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    combined_findings.sort(key=lambda item: severity_rank.get(item.get("severity", "medium"), 1))

    improvements = []
    if final_score < 90:
        for finding in combined_findings:
            message = finding.get("message", "").strip()
            improvement = finding.get("improvement", "").strip()
            if not message or not improvement:
                continue
            text_item = f"{message} -> {improvement}"
            if text_item not in improvements:
                improvements.append(text_item)

    return {
        "score": final_score,
        "weights": weights,
        "improvements_required": final_score < 90,
        "improvement_items": improvements,
        "findings": combined_findings,
    }


def score_skill(
    project_root: Path,
    skill_file: Path,
    skip_tests: bool,
) -> dict:
    skill_dir = skill_file.parent
    skill_name = skill_dir.name
    rel_skill_file = str(skill_file.relative_to(project_root))
    lines = skill_file.read_text(encoding="utf-8").splitlines(keepends=True)
    text = "".join(lines)
    frontmatter = parse_frontmatter(lines)
    findings: list[Finding] = []

    # 1) Metadata & use-case clarity (max 20)
    metadata_score = 0
    if frontmatter:
        metadata_score += 8
    else:
        findings.append(
            Finding(
                severity="high",
                path=rel_skill_file,
                line=1,
                message="Frontmatter is missing or malformed.",
                improvement="Add valid YAML frontmatter with `name` and `description`.",
            )
        )

    declared_name = frontmatter.get("name")
    if declared_name:
        metadata_score += 6
        if declared_name != skill_name:
            findings.append(
                Finding(
                    severity="medium",
                    path=rel_skill_file,
                    line=find_line(lines, r"^name:\s"),
                    message=f"`name` does not match directory name (`{declared_name}` vs `{skill_name}`).",
                    improvement="Align frontmatter `name` with the skill folder name.",
                )
            )
        else:
            metadata_score += 6
    else:
        findings.append(
            Finding(
                severity="high",
                path=rel_skill_file,
                line=find_line(lines, r"^---"),
                message="Frontmatter `name` is missing.",
                improvement="Add `name: <skill-folder-name>` to frontmatter.",
            )
        )

    # 2) Workflow coverage (max 25)
    workflow_score = 0
    required_sections = {
        "When to Use": [r"^##\s*When to Use", r"^##\s*When to Use This Skill"],
        "Prerequisites": [r"^##\s*Prerequisites", r"^##\s*Input Requirements"],
        "Workflow": [r"^##\s*Workflow", r"^##\s*Execution Workflow", r"^##\s*Evaluation Process"],
        "Output": [r"^##\s*Output", r"^##\s*Output Files"],
        "Resources": [r"^##\s*Resources", r"^##\s*Reference Documents", r"^##\s*Data Sources"],
    }
    for section_name, heading_patterns in required_sections.items():
        if has_heading(text, heading_patterns):
            workflow_score += 5
        else:
            findings.append(
                Finding(
                    severity="medium",
                    path=rel_skill_file,
                    line=None,
                    message=f"Missing section: `## {section_name}`.",
                    improvement=f"Add `## {section_name}` to improve operator guidance.",
                )
            )

    # 3) Execution safety & reproducibility (max 25)
    exec_score = 0
    bash_blocks = extract_bash_blocks(text)
    if bash_blocks:
        exec_score += 8
    else:
        findings.append(
            Finding(
                severity="medium",
                path=rel_skill_file,
                line=None,
                message="No runnable bash examples found.",
                improvement="Add executable command examples in a `bash` code block.",
            )
        )

    skill_script_prefix = f"skills/{skill_name}/scripts/"
    if any(skill_script_prefix in block for block in bash_blocks):
        exec_score += 6
    else:
        findings.append(
            Finding(
                severity="low",
                path=rel_skill_file,
                line=None,
                message="Examples do not clearly anchor script paths from repository root.",
                improvement=f"Use repo-root paths like `{skill_script_prefix}...` in commands.",
            )
        )

    output_dir_values = collect_output_dir_values(bash_blocks)
    unsafe_output_dir = any("/scripts" in value or value.endswith("scripts") for value in output_dir_values)
    if output_dir_values and not unsafe_output_dir:
        exec_score += 6
    elif output_dir_values and unsafe_output_dir:
        findings.append(
            Finding(
                severity="medium",
                path=rel_skill_file,
                line=find_line(lines, r"--output-dir"),
                message="Sample commands write generated reports into source `scripts/` directory.",
                improvement="Use a dedicated output path like `reports/` to avoid source tree pollution.",
            )
        )
    else:
        exec_score += 3

    if re.search(r"export\s+FMP_API_KEY=", text) or re.search(r"--api-key\s+\S+", text):
        exec_score += 5
    elif "FMP_API_KEY" in text:
        exec_score += 2
        findings.append(
            Finding(
                severity="low",
                path=rel_skill_file,
                line=find_line(lines, r"FMP_API_KEY"),
                message="API key is documented, but no copy-paste setup command is shown.",
                improvement="Add an explicit example like `export FMP_API_KEY=...`.",
            )
        )

    ref_paths = re.findall(r"`([^`]*references/[^`]*)`", text)
    if not ref_paths:
        exec_score += 3
    else:
        fully_qualified = [
            p for p in ref_paths if p.startswith(f"skills/{skill_name}/references/")
        ]
        if len(fully_qualified) == len(ref_paths):
            exec_score += 5
        else:
            exec_score += 2
            findings.append(
                Finding(
                    severity="low",
                    path=rel_skill_file,
                    line=find_line(lines, r"references/"),
                    message="Reference paths are mostly relative and may be ambiguous from project root.",
                    improvement=(
                        f"Prefer explicit paths like `skills/{skill_name}/references/...` "
                        "in operator instructions."
                    ),
                )
            )

    # 4) Supporting artifacts (max 10)
    artifact_score = 0
    ref_count = len(list((skill_dir / "references").glob("*.md")))
    script_count = len(list((skill_dir / "scripts").glob("*.py")))
    test_count = len(list((skill_dir / "scripts" / "tests").glob("test_*.py")))

    if ref_count > 0:
        artifact_score += 4
    else:
        findings.append(
            Finding(
                severity="medium",
                path=rel_skill_file,
                line=None,
                message="No markdown reference files found in `references/`.",
                improvement="Add methodology/reference docs to support consistent interpretation.",
            )
        )

    if script_count > 0:
        artifact_score += 3
    else:
        findings.append(
            Finding(
                severity="medium",
                path=rel_skill_file,
                line=None,
                message="No executable helper scripts found in `scripts/`.",
                improvement="Add automation scripts for repeatable execution.",
            )
        )

    if test_count > 0:
        artifact_score += 3
    else:
        findings.append(
            Finding(
                severity="medium",
                path=rel_skill_file,
                line=None,
                message="No `test_*.py` tests found for skill scripts.",
                improvement="Add skill-level tests under `scripts/tests/`.",
            )
        )

    # 5) Test health (max 20)
    test_score = 0
    test_status = "skipped"
    test_command: str | None = None
    test_output = ""
    if skip_tests:
        test_status = "skipped"
        test_score = 8 if test_count > 0 else 0
    else:
        test_status, test_command, test_output = run_tests(project_root, skill_dir)
        if test_status == "passed":
            test_score = 20
        elif test_status in {"not_found", "tool_missing"}:
            test_score = 6 if test_count > 0 else 0
        elif test_status == "timeout":
            test_score = 2
            findings.append(
                Finding(
                    severity="medium",
                    path=rel_skill_file,
                    line=None,
                    message="Skill tests timed out; health could not be verified.",
                    improvement="Optimize tests or split slower integration tests.",
                )
            )
        else:
            findings.append(
                Finding(
                    severity="high",
                    path=rel_skill_file,
                    line=None,
                    message="Skill tests failed.",
                    improvement="Fix failing tests before relying on this skill in automation.",
                )
            )

    total_score = metadata_score + workflow_score + exec_score + artifact_score + test_score
    total_score = max(0, min(100, total_score))

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda item: severity_rank[item.severity])

    improvements = []
    if total_score < 90:
        for finding in findings:
            text_item = f"{finding.message} -> {finding.improvement}"
            if text_item not in improvements:
                improvements.append(text_item)

    return {
        "skill_name": skill_name,
        "skill_file": rel_skill_file,
        "score": total_score,
        "score_breakdown": {
            "metadata_use_case": metadata_score,
            "workflow_coverage": workflow_score,
            "execution_safety_reproducibility": exec_score,
            "supporting_artifacts": artifact_score,
            "test_health": test_score,
        },
        "findings": [
            {
                "severity": f.severity,
                "path": f.path,
                "line": f.line,
                "message": f.message,
                "improvement": f.improvement,
            }
            for f in findings
        ],
        "improvements_required": total_score < 90,
        "improvement_items": improvements,
        "test_status": test_status,
        "test_command": test_command,
        "test_output": test_output,
    }


def to_markdown(report: dict) -> str:
    auto_review = report["auto_review"]
    llm_review = report["llm_review"]
    final_review = report["final_review"]

    lines = [
        "# Dual-Axis Skill Review",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Selected skill: `{report['skill_name']}`",
        f"- Skill file: `{report['skill_file']}`",
        f"- Selection mode: `{report['selection_mode']}`",
        f"- Seed: `{report['seed']}`",
        f"- Auto score: **{auto_review['score']} / 100**",
        f"- LLM score: **{llm_review['score']} / 100**" if llm_review["provided"] else "- LLM score: `not provided`",
        f"- Final score: **{final_review['score']} / 100**",
        "",
        "## Auto Score Breakdown",
    ]
    for key, value in auto_review["score_breakdown"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(
        [
            "",
            "## Score Weights",
            f"- auto_weight: {final_review['weights']['auto_weight']:.2f}",
            f"- llm_weight: {final_review['weights']['llm_weight']:.2f}",
        ]
    )

    lines.extend(["", "## Findings (Combined)"])
    if final_review["findings"]:
        for idx, finding in enumerate(final_review["findings"], start=1):
            loc = finding.get("path", "")
            if finding.get("line"):
                loc = f"{loc}:{finding['line']}"
            lines.append(
                f"{idx}. [{finding.get('axis', 'unknown').upper()}|"
                f"{finding.get('severity', 'medium').upper()}] `{loc}` - "
                f"{finding.get('message', '').strip()}"
            )
    else:
        lines.append("- No notable findings.")

    lines.extend(
        [
            "",
            "## Test Verification (Auto Axis)",
            f"- Status: `{auto_review['test_status']}`",
            f"- Command: `{auto_review['test_command']}`",
        ]
    )

    if report.get("llm_prompt_file"):
        lines.extend(["", "## LLM Prompt File", f"- `{report['llm_prompt_file']}`"])

    if final_review["improvements_required"]:
        lines.extend(["", "## Improvement Items (Final Score < 90)"])
        for idx, item in enumerate(final_review["improvement_items"], start=1):
            lines.append(f"{idx}. {item}")

    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    skills = discover_skills(project_root)
    if not skills:
        print("No skills found at skills/*/SKILL.md", file=sys.stderr)
        return 1

    try:
        selected = pick_skill(skills, args.skill, args.seed)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    auto_review = score_skill(
        project_root=project_root,
        skill_file=selected,
        skip_tests=args.skip_tests,
    )

    try:
        llm_review = load_llm_review(args.llm_review_json, project_root)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Invalid --llm-review-json: {exc}", file=sys.stderr)
        return 1
    if llm_review is None:
        llm_review = {
            "provided": False,
            "source_file": None,
            "score": None,
            "summary": "",
            "findings": [],
        }

    final_review = combine_reviews(
        auto_review=auto_review,
        llm_review=llm_review if llm_review["provided"] else None,
        auto_weight=args.auto_weight,
        llm_weight=args.llm_weight,
    )

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output_dir = (project_root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    stem = f"skill_review_{auto_review['skill_name']}_{timestamp}"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"

    llm_prompt_file = None
    if args.emit_llm_prompt:
        prompt_file = output_dir / f"skill_review_prompt_{auto_review['skill_name']}_{timestamp}.md"
        prompt_file.write_text(
            build_llm_prompt(project_root, selected.parent, auto_review),
            encoding="utf-8",
        )
        llm_prompt_file = str(prompt_file)

    report = {
        "generated_at": generated_at,
        "seed": args.seed,
        "selection_mode": "manual" if args.skill else "random",
        "skill_name": auto_review["skill_name"],
        "skill_file": auto_review["skill_file"],
        "auto_review": auto_review,
        "llm_review": llm_review,
        "final_review": final_review,
        "llm_prompt_file": llm_prompt_file,
    }

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(to_markdown(report), encoding="utf-8")

    print(f"Selected skill: {auto_review['skill_name']}")
    print(f"Auto score: {auto_review['score']}/100")
    if llm_review["provided"]:
        print(f"LLM score: {llm_review['score']}/100")
    print(f"Final score: {final_review['score']}/100")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")
    if llm_prompt_file:
        print(f"LLM prompt: {llm_prompt_file}")
    if auto_review["test_status"] == "passed":
        summary_line = next(
            (
                line
                for line in auto_review["test_output"].splitlines()
                if " passed" in line
            ),
            "",
        )
        if summary_line:
            print(f"Tests: {summary_line.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
