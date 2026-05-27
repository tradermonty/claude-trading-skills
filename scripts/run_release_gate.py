"""CI release gate for TraderMonty.

Runs all institutional-grade quality checks required before a package release
or deployment.  Exits 0 if all checks pass, 1 if any check fails.

Usage:
    python3 scripts/run_release_gate.py [--quick] [--strict]

Options:
    --quick    Skip the full pytest run (just run validators)
    --strict   Also verify audit log chain and check for signing ceremony
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))


def _run(label: str, cmd: list[str], cwd: Path | None = None) -> bool:
    """Run a command, print its output, and return True if it exited 0."""
    print(f"\n{'=' * 60}")
    print(f"CHECK: {label}")
    print(f"CMD:   {' '.join(cmd)}")
    print("=" * 60)
    result = subprocess.run(cmd, cwd=cwd or REPO_ROOT)
    ok = result.returncode == 0
    status = "PASS" if ok else "FAIL"
    print(f"\n[{status}] {label}")
    return ok


def _grep_oanda(repo_root: Path) -> bool:
    """Check that no non-test Python file imports oanda_trader.

    Uses the same precise regex patterns as TestOandaIntegrationBoundary
    in test_repo_hardening.py — avoids false positives when the string
    'oanda_trader' appears inside a string literal or comment in a validator.
    """
    import re as _re

    print(f"\n{'=' * 60}")
    print("CHECK: OANDA boundary — no oanda_trader imports in production code")
    print("=" * 60)
    _PATTERNS = [
        _re.compile(r"\bfrom\s+oanda_trader\b"),
        _re.compile(r"\bimport\s+oanda_trader\b"),
        _re.compile(r"\bfrom\s+oanda\.trader\b"),
    ]
    violations = []
    for py_file in repo_root.rglob("*.py"):
        parts = py_file.parts
        if any(p in ("__pycache__", "tests") for p in parts):
            continue
        if py_file.name.startswith("test_"):
            continue
        try:
            text = py_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(pat.search(text) for pat in _PATTERNS):
            violations.append(str(py_file.relative_to(repo_root)))

    if violations:
        print("[FAIL] Found oanda_trader import(s) in production code:")
        for v in violations:
            print(f"       {v}")
        return False
    print("[PASS] OANDA boundary — no oanda_trader imports in production code")
    return True


def _check_forbidden_language(repo_root: Path) -> bool:
    """Scan SKILL.md files for forbidden execution-oriented language.

    Context-aware: occurrences that are immediately negated in the same
    clause (e.g. "this skill does not place orders") are ignored because
    those phrases reinforce the decision-support boundary rather than
    violating it.  Specifically, any forbidden phrase is skipped when a
    negation word (not, never, don't, doesn't, cannot, do not, does not,
    won't) appears in the 120 characters preceding it with no intervening
    sentence boundary (`.  `, `!  `, `?  `, or newline after the negation).
    """
    import re as _re

    print(f"\n{'=' * 60}")
    print("CHECK: Forbidden language in SKILL.md files")
    print("=" * 60)
    forbidden = [
        "execute order", "submit order", "place order",
        "buy at market", "sell at market", "buy now", "sell now",
        "auto-trade", "auto trade",
    ]
    _NEGATION = _re.compile(
        r"\b(not|never|don'?t|doesn'?t|cannot|do not|does not|won'?t)\b",
        _re.IGNORECASE,
    )
    violations: list[str] = []
    for skill_md in repo_root.rglob("SKILL.md"):
        try:
            text = skill_md.read_text(encoding="utf-8", errors="ignore")
            text_lower = text.lower()
        except OSError:
            continue
        for phrase in forbidden:
            start = 0
            while True:
                idx = text_lower.find(phrase, start)
                if idx == -1:
                    break
                # Build the lookback window: text from last sentence boundary
                # (or up to 120 chars back) to the phrase start.
                window_start = max(0, idx - 120)
                lookback = text_lower[window_start:idx]
                # Trim to last sentence boundary within the window
                for sep in (". ", "! ", "? ", "\n"):
                    last_sep = lookback.rfind(sep)
                    if last_sep != -1:
                        lookback = lookback[last_sep + len(sep):]
                if not _NEGATION.search(lookback):
                    rel = skill_md.relative_to(repo_root)
                    violations.append(f"{rel}: contains '{phrase}'")
                start = idx + 1

    if violations:
        print("[FAIL] Forbidden execution language found:")
        for v in violations:
            print(f"       {v}")
        return False
    print("[PASS] No forbidden execution language in SKILL.md files")
    return True


def _check_audit_log_chain(repo_root: Path) -> bool:
    """Verify audit log hash chain integrity (skip if log absent)."""
    print(f"\n{'=' * 60}")
    print("CHECK: Audit log hash chain")
    print("=" * 60)
    try:
        from audit_log import AuditLog  # noqa: PLC0415
    except ImportError:
        print("[SKIP] audit_log module not available")
        return True

    log = AuditLog(repo_root / "state" / "audit-log")
    if not log.log_file.exists():
        print("[SKIP] Audit log does not exist yet — nothing to verify")
        return True

    errors = log.verify_chain()
    if errors:
        print("[FAIL] Audit log chain errors:")
        for e in errors:
            print(f"       {e}")
        return False

    entry_count = len(log.entries())
    print(f"[PASS] Audit log chain valid ({entry_count} entries)")
    return True


def _check_ceremony_log(repo_root: Path, strict: bool = False) -> bool:
    """Verify ceremony log chain; in --strict mode, require a PACKAGE_SIGNING ceremony."""
    print(f"\n{'=' * 60}")
    print("CHECK: Ceremony log" + (" (strict)" if strict else ""))
    print("=" * 60)
    try:
        from ceremony_log import CeremonyLog, CeremonyType  # noqa: PLC0415
    except ImportError:
        print("[SKIP] ceremony_log module not available")
        return True

    log = CeremonyLog(repo_root / "state" / "ceremony-log")
    if not log.log_file.exists():
        if strict:
            print("[FAIL] Ceremony log absent — run package signing ceremony first")
            return False
        print("[SKIP] Ceremony log does not exist yet — nothing to verify")
        return True

    errors = log.verify_chain()
    if errors:
        print("[FAIL] Ceremony log chain errors:")
        for e in errors:
            print(f"       {e}")
        return False

    if strict:
        has_signing = log.has_recent_ceremony(CeremonyType.PACKAGE_SIGNING)
        if not has_signing:
            print("[FAIL] No PACKAGE_SIGNING ceremony found — sign packages before release")
            return False
        print("[PASS] Ceremony log valid and PACKAGE_SIGNING ceremony present")
    else:
        print(f"[PASS] Ceremony log chain valid ({len(log.entries())} entries)")

    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--quick", action="store_true", help="Skip the full pytest run")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also verify audit log, ceremony log, and require signing ceremony",
    )
    args = parser.parse_args(argv)

    results: list[tuple[str, bool]] = []

    # 1. Full schema + script tests (skipped with --quick)
    if not args.quick:
        ok = _run(
            "Full pytest suite (schemas/tests + scripts/tests)",
            [sys.executable, "-m", "pytest", "schemas/tests/", "scripts/tests/", "-q"],
        )
        results.append(("pytest", ok))
    else:
        print("\n[SKIP] Full pytest suite (--quick mode)")

    # 2. Workflow validation
    ok = _run(
        "Workflow validation",
        [sys.executable, "scripts/workflow_runner.py", "validate"],
    )
    results.append(("workflow-validate", ok))

    # 3. Skills index validation
    ok = _run(
        "Skills index validation",
        [sys.executable, "scripts/validate_skills_index.py"],
    )
    results.append(("skills-index-validate", ok))

    # 4. Artifact validation
    ok = _run(
        "Artifact validation (--all)",
        [sys.executable, "scripts/validate_artifacts.py", "--all"],
    )
    results.append(("artifact-validate", ok))

    # 5. Package verification (dev mode)
    ok = _run(
        "Package verification (dev key)",
        [sys.executable, "scripts/manage_skill_packages.py", "verify", "--dev-mode", "--dev-key"],
    )
    results.append(("package-verify", ok))

    # 6. OANDA boundary
    ok = _grep_oanda(REPO_ROOT)
    results.append(("oanda-boundary", ok))

    # 7. Forbidden language
    ok = _check_forbidden_language(REPO_ROOT)
    results.append(("forbidden-language", ok))

    # 8. Audit log chain (always; strict adds ceremony check)
    ok = _check_audit_log_chain(REPO_ROOT)
    results.append(("audit-log-chain", ok))

    # 9. Ceremony log (skip in non-strict if absent; strict requires signing ceremony)
    ok = _check_ceremony_log(REPO_ROOT, strict=args.strict)
    results.append(("ceremony-log", ok))

    # Summary
    print(f"\n{'=' * 60}")
    print("RELEASE GATE SUMMARY")
    print("=" * 60)
    passed = 0
    failed = 0
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        mark = "✓" if ok else "✗"
        print(f"  {mark} [{status}] {name}")
        if ok:
            passed += 1
        else:
            failed += 1

    print(f"\n{passed + failed} check(s): {passed} passed, {failed} failed")

    if failed:
        print("\n[BLOCKED] Release gate FAILED — fix the issues above before releasing.")
        return 1
    print("\n[OK] Release gate PASSED — all checks green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
