#!/usr/bin/env python3
"""Validate that documented CLI examples stay runnable (issue #336).

Regression gate for stale documented commands (cf. #265 nonexistent
script, #311 required API key). Enforces, offline and deterministically,
that examples explicitly marked as executable keep referencing an
existing script, passing options that the script actually accepts, and
staying consistent across EN/JA paired pages. Nothing is executed by
``validate``; optional offline execution lives in the opt-in ``execute``
subcommand.

Marker grammar (HTML comment on the line immediately above a fenced bash
block; renderer-invisible and outside every generator's fence-capture so
it never leaks into generated docs):

    <!-- exec: offline -->              runnable offline (may be executed)
    <!-- exec: offline ci -->          offline AND wired into the CI execute job
    <!-- exec: api -->                 requires an API key / network; statically
                                       validated, never executed
    <!-- exec: skip reason="..." owner="..." expires=YYYY-MM-DD -->
                                       opt-out; reason/owner/expires mandatory,
                                       an expired skip is an error

Subcommands:
  validate   offline static gate: script existence, option acceptance,
             EN/JA script parity, skip policy (default; used by pre-commit
             and the CI job).
  execute    opt-in: run ``offline ci`` (or, with --ci) / ``offline``
             blocks inside a temp dir so repository state is never
             mutated. Not run by CI validate; call it explicitly.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# HTML-comment marker on the line above a fenced bash block.
MARKER_RE = re.compile(r"<!--\s*exec:\s*(.*?)\s*-->")
VALID_MODES = ("offline", "api", "skip")
SKIP_KEYS = ("reason", "owner", "expires")
DEFAULT_TARGETS = ["CLAUDE.md", "README.md", "README.ja.md", "skills/*/SKILL.md"]
# EN/JA command-parity pairs, ":":-separated file paths relative to ROOT.
DEFAULT_EN_JA_PAIRS = ["README.md:README.ja.md"]
# Env vars stripped from any executed example so a CI example cannot reach a
# paid API on a leaked key.
API_KEY_ENV_VARS = (
    "FMP_API_KEY",
    "FINVIZ_API_KEY",
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
)


@dataclass
class Marker:
    line_no: int
    mode: str  # offline | api | skip
    ci: bool
    skip: dict  # reason/owner/expires when mode == skip


@dataclass
class Finding:
    file: str
    line_no: int
    message: str

    def render(self) -> str:
        return f"{self.file}:{self.line_no}: {self.message}"


# ---------------------------------------------------------------------------
# Markdown scanning
# ---------------------------------------------------------------------------


def _kv(body: str, key: str) -> str:
    m = re.search(rf"""{key}\s*=\s*("(?:[^"\\]|\\.)*"|'[^']*'|[^\s"']+)""", body)
    if not m:
        return ""
    return m.group(1).strip("\"'")


def _parse_marker(body: str) -> Marker:
    parts = body.split(None, 1)
    head = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    if head == "skip":
        kv: dict = {k: _kv(rest, k) for k in SKIP_KEYS}
        return Marker(0, "skip", False, kv)
    ci = "ci" in rest.split()
    return Marker(0, head, ci, {})


def scan_targets(paths: list[Path]) -> list[tuple[Path, list[tuple[Marker, str]]]]:
    """Return (path, [(Marker, fenced_bash_content), ...]) per target."""
    results = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        blocks: list[tuple[Marker, str]] = []
        pending: Marker | None = None
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            m = MARKER_RE.search(line)
            if m:
                # only keep the last marker before the fence
                pending = _parse_marker(m.group(1))
                pending.line_no = i + 1
                i += 1
                continue
            if stripped.startswith("```") and "bash" in stripped.lstrip("`"):
                # collect fenced content until closing fence
                if pending is not None:
                    fence_lines = []
                    i += 1
                    while i < len(lines) and not lines[i].strip().startswith("```"):
                        fence_lines.append(lines[i])
                        i += 1
                    blocks.append((pending, "\n".join(fence_lines)))
                pending = None
                i += 1
                continue
            # any non-empty, non-marker content breaks marker->fence adjacency
            if pending is not None and stripped and not stripped.startswith("#"):
                pending = None
            i += 1
        results.append((path, blocks))
    return results


def extract_invocations(block: str) -> list[list[str]]:
    """Return the ``python<ver> <script> [args]`` token-lists in a block.

    Backslash-continuation lines are joined first so a multi-line command is
    one invocation rather than a headless ``python <script>`` that would break
    the static and execute gates.
    """
    logical: list[str] = []
    buf = ""
    for line in block.splitlines():
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            buf += stripped[:-1] + " "
        else:
            buf += stripped
            logical.append(buf)
            buf = ""
    if buf:
        logical.append(buf)

    invs: list[list[str]] = []
    for line in logical:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            toks = shlex.split(line, comments=True)
        except ValueError:
            # Tolerate stray backslashes / malformed quoting; fall back to a
            # whitespace split sufficient for command detection.
            toks = line.replace("\\", " ").split()
        if not toks:
            continue
        if toks[0] == "uv" and len(toks) > 1 and toks[1] == "run":
            toks = toks[2:]
        if not toks:
            continue
        if toks[0] in ("python3", "python"):
            invs.append(toks)
    return invs


# ---------------------------------------------------------------------------
# Static option acceptance (AST, never executed)
# ---------------------------------------------------------------------------


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def collect_options(script: Path) -> tuple[set[str], bool]:
    """Return (accepted option strings, has_parser).

    Scans ``add_argument`` / ``add_option`` / ``add_parser`` calls in the
    script file via AST. Subparser-recursive: options declared anywhere in
    the file (including per-command parser functions) are captured, so no
    execution or import is required. Returns (set(), False) when the script
    defines no arg parser at all.
    """
    try:
        tree = ast.parse(script.read_text(encoding="utf-8"))
    except SyntaxError:
        return set(), False
    accepted: set[str] = set()
    has_parser = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in ("add_argument", "add_option", "add_parser"):
                has_parser = True
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        accepted.add(arg.value)
    return accepted, has_parser


def documented_options(toks: list[str]) -> list[str]:
    """Return option names (``-x`` / ``--xyz``) from an invocation.

    ``--foo=value`` is reduced to ``--foo``, and negative numeric values such
    as ``-1`` (a value, not a flag) are excluded so they are never compared
    against the accepted option set.
    """
    opts: list[str] = []
    for t in toks[2:]:
        if not t.startswith("-") or len(t) <= 1:
            continue
        name = t.split("=", 1)[0]
        if not re.match(r"^-{1,2}[A-Za-z]", name):
            continue
        opts.append(name)
    return opts


# ---------------------------------------------------------------------------
# EN/JA parity
# ---------------------------------------------------------------------------


def collect_script_refs(path: Path) -> set[str]:
    """Collect normalized script paths from fences and inline backtick spans."""
    refs: set[str] = set()
    text = path.read_text(encoding="utf-8")
    for _, block in scan_targets([path])[0][1]:
        for toks in extract_invocations(block):
            refs.add(_normalize_script(toks))
    inline = re.findall(r"`([^`]*?\bpython3?\s+[\w./\-\"]+[^`]*)`", text)
    for span in inline:
        try:
            toks = shlex.split(span, comments=True)
        except ValueError:
            continue
        for i, t in enumerate(toks):
            if t in ("python3", "python") and i + 1 < len(toks):
                refs.add(_normalize_script(toks[i:]))
                break
    return refs


def _normalize_script(toks: list[str]) -> str:
    script = toks[1]
    return script.strip("\"'")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_target(
    path: Path, blocks: list[tuple[Marker, str]], findings: list[Finding], root: Path = ROOT
) -> None:
    today = date.today()
    for marker, block in blocks:
        if marker.mode not in VALID_MODES:
            findings.append(
                Finding(
                    str(path),
                    marker.line_no,
                    f"unknown exec marker mode: {marker.mode!r} "
                    f"(expected one of {', '.join(VALID_MODES)})",
                )
            )
            continue
        if marker.mode == "skip":
            skip = marker.skip
            if not all(skip.get(k) for k in SKIP_KEYS):
                findings.append(
                    Finding(
                        str(path),
                        marker.line_no,
                        "skip marker requires reason=, owner=, and expires=YYYY-MM-DD",
                    )
                )
                continue
            try:
                exp = datetime.strptime(skip["expires"], "%Y-%m-%d").date()
            except ValueError:
                findings.append(
                    Finding(
                        str(path),
                        marker.line_no,
                        f"skip expires is not YYYY-MM-DD: {skip['expires']!r}",
                    )
                )
                continue
            if today > exp:
                findings.append(
                    Finding(
                        str(path),
                        marker.line_no,
                        f"skip is expired (expires {skip['expires']}): {skip['reason']}",
                    )
                )
            continue

        if marker.ci and marker.mode == "api":
            findings.append(Finding(str(path), marker.line_no, "api-marked block cannot be ci"))
            continue

        for toks in extract_invocations(block):
            if len(toks) < 2:
                continue
            script_rel = _normalize_script(toks)
            script = root / script_rel
            if not script.exists():
                findings.append(
                    Finding(str(path), marker.line_no, f"script does not exist: {script_rel}")
                )
                continue
            accepted, has_parser = collect_options(script)
            doc_opts = documented_options(toks)
            if not has_parser:
                if doc_opts:
                    findings.append(
                        Finding(
                            str(path),
                            marker.line_no,
                            f"{script_rel} defines no argparse parser but documented "
                            f"options are passed: {' '.join(doc_opts)} (use a skip marker if "
                            f"intentional; implement the CLI to make the example runnable)",
                        )
                    )
                continue
            for opt in doc_opts:
                if opt not in accepted:
                    findings.append(
                        Finding(
                            str(path), marker.line_no, f"option not accepted by {script_rel}: {opt}"
                        )
                    )


def validate_en_ja_pairs(pairs: list[str], findings: list[Finding], root: Path = ROOT) -> None:
    for pair in pairs:
        en_rel, ja_rel = pair.split(":", 1)
        en, ja = root / en_rel, root / ja_rel
        if not en.exists() or not ja.exists():
            findings.append(Finding(pair, 0, "pair file missing"))
            continue
        en_refs = collect_script_refs(en)
        ja_refs = collect_script_refs(ja)
        for ref in sorted(en_refs - ja_refs):
            findings.append(Finding(str(en), 0, f"command present in EN but missing in JA: {ref}"))
        for ref in sorted(ja_refs - en_refs):
            findings.append(Finding(str(ja), 0, f"command present in JA but missing in EN: {ref}"))


def _expand_targets(root: Path, targets: list[str]) -> list[Path]:
    """Expand target patterns (globs allowed) to existing file paths under root.

    A non-matching, glob-free target is kept so ``run_validate`` can report it
    as missing; glob patterns that match nothing expand to nothing.
    """
    expanded: list[Path] = []
    for target in targets:
        pattern = root / target
        if not Path(target).name and not target.endswith("*"):
            # explicit directory-ish entry; keep for the missing-file report
            expanded.append(pattern)
            continue
        matches = sorted(root.glob(target)) if any(ch in target for ch in "*?[") else []
        if matches:
            expanded.extend(p for p in matches if p.is_file())
        elif not any(ch in target for ch in "*?["):
            expanded.append(pattern)
    return expanded


def _git_status_snapshot(root: Path) -> str | None:
    """Disconnected-mutation guard: repo status text, or None when not a repo.

    ``None`` means the guard is disabled (no ``git`` available or ``root`` is
    not a repository, which is the normal case for test fixtures).

    All ``GIT_*`` variables are scrubbed from the child environment: hooks
    (pre-push and friends) export ``GIT_DIR`` / ``GIT_INDEX_FILE`` /
    ``GIT_WORK_TREE``, and inheriting them makes an unrelated directory report
    against the hooking repo's index (everything reads as deleted) instead of
    honouring ``-C <other-dir>`` discovery.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def run_validate(targets: list[str], en_ja_pairs: list[str], root: Path = ROOT) -> list[Finding]:
    findings: list[Finding] = []
    for path in _expand_targets(root, targets):
        if not path.is_file():
            findings.append(Finding(str(path), 0, "target file missing"))
            continue
        for path_, blocks in scan_targets([path]):
            validate_target(path_, blocks, findings, root=root)
    validate_en_ja_pairs(en_ja_pairs, findings, root=root)
    return findings


# ---------------------------------------------------------------------------
# Execute (opt-in offline, temp-dir isolated)
# ---------------------------------------------------------------------------


def run_execute(
    targets: list[str], ci_only: bool, root: Path = ROOT
) -> tuple[list[str], list[str]]:
    """Run eligible blocks in a temp cwd. Returns (ran_ok, errors).

    Two isolation layers protect the originating repository:
    - each invocation runs with ``cwd`` set to a fresh temp dir, so
      cwd-relative outputs (``reports/`` etc.) never land in the repo;
    - a before/after ``git status --porcelain`` delta check around each block
      catches any write that escapes the temp cwd by other means (absolute
      repo paths, ``../`` arguments, or absolute target args) and fails the
      block that caused it. The delta check is skipped for non-git roots.
    ``ci_only`` runs additionally execute under ``python3 -S`` (stdlib only),
    so a block marked ``offline ci`` cannot quietly rely on an undeclared
    third-party dependency present in the CI environment.
    """
    errors: list[str] = []
    ran: list[str] = []
    for path, blocks in scan_targets(_expand_targets(root, targets)):
        for marker, block in blocks:
            if marker.mode != "offline":
                continue
            if ci_only and not marker.ci:
                continue
            for toks in extract_invocations(block):
                if len(toks) < 2:
                    continue
                script = root / _normalize_script(toks)
                if not script.exists():
                    errors.append(f"{path}:{marker.line_no}: missing script {script}")
                    continue
                before = _git_status_snapshot(root)
                with tempfile.TemporaryDirectory() as td:
                    env = dict(os.environ)
                    for k in API_KEY_ENV_VARS:
                        env.pop(k, None)
                    cmd = ["python3", str(script)] + toks[2:]
                    if ci_only:
                        cmd.insert(1, "-S")
                    try:
                        proc = subprocess.run(
                            cmd, cwd=td, env=env, capture_output=True, text=True, timeout=120
                        )
                    except subprocess.TimeoutExpired:
                        errors.append(f"{path}:{marker.line_no}: timeout running {script}")
                        continue
                    if proc.returncode != 0:
                        errors.append(
                            f"{path}:{marker.line_no}: exit {proc.returncode} running {script}\n"
                            f"    stdout: {proc.stdout[-400:].strip()}\n"
                            f"    stderr: {proc.stderr[-400:].strip()}"
                        )
                        continue
                if before is not None:
                    after = _git_status_snapshot(root)
                    if after != before:
                        errors.append(
                            f"{path}:{marker.line_no}: {script} mutated the repository "
                            f"during execution (git status changed); remove repo-targeting "
                            f"arguments from the example or mark it skip"
                        )
                        continue
                ran.append(f"{path}:{marker.line_no}: {script}")
    return ran, errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate documented CLI examples (issue #336)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("validate", help="offline static gate (pre-commit + CI)")
    pv.add_argument("--targets", nargs="*", default=DEFAULT_TARGETS)
    pv.add_argument("--en-ja-pairs", nargs="*", default=DEFAULT_EN_JA_PAIRS)

    pe = sub.add_parser("execute", help="run offline examples in a temp cwd (opt-in)")
    pe.add_argument("--targets", nargs="*", default=DEFAULT_TARGETS)
    pe.add_argument("--ci", action="store_true", help="only run blocks marked `offline ci`")

    args = parser.parse_args(argv)

    if args.cmd == "validate":
        findings = run_validate(args.targets, args.en_ja_pairs)
        if findings:
            for f in findings:
                print(f.render(), file=sys.stderr)
            sys.exit(1)
        print("OK: documented CLI examples validate")
        return 0

    if args.cmd == "execute":
        ran, errors = run_execute(args.targets, getattr(args, "ci", False))
        for r in ran:
            print(f"executed: {r}")
        if errors:
            for e in errors:
                print(e, file=sys.stderr)
            sys.exit(1)
        if not ran:
            print("execute: no eligible offline blocks found")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
