"""Skill package integrity manager.

Commands:
  sign      — Compute SHA-256 for every .skill file, sign the manifest, and write
              skill-packages/checksums.json
  verify    — Compare current hashes against checksums.json and verify the
              HMAC-SHA256 manifest signature; exit 1 on any failure
  list      — Print table of packages with staleness (FRESH / STALE) relative to SKILL.md

Cryptographic signing (Phase 1 — Third Hardening Pass)
-------------------------------------------------------
Manifests are now signed with HMAC-SHA256.  The signature covers the canonical
JSON of the manifest (sorted keys, no whitespace) with the ``_signature`` and
``_signature_key_id`` fields stripped before hashing, so those fields can be
stored alongside the data.

Key sources (in priority order):
  1. ``TRADERMONTY_SIGNING_KEY`` environment variable (hex-encoded 32+ bytes)
  2. Dev key file at ``~/.config/tradermonty/dev-signing.key``
  3. Auto-generated dev key (if --dev-key flag is passed to sign)

Pass ``--dev-mode`` to verify to accept unsigned manifests with a warning.
See ``scripts/signing.py`` and ``docs/internal/key-management.md`` for details.

Release metadata (Phase 6 upgrade)
-----------------------------------
``sign`` captures build-time metadata into checksums.json under a ``_release`` key:
  - ``manifest_version``: schema version for the manifest format
  - ``build_timestamp``:  ISO-8601 UTC timestamp of when sign was run
  - ``source_commit``:    git commit hash at sign time (empty string if unavailable)
  - ``source_dirty``:     True if working tree had uncommitted changes at sign time
  - ``signed_by``:        value of --signed-by flag (defaults to "unspecified")
  - ``signing_note``:     human-readable note about the signing approach
  - ``_signature``:       HMAC-SHA256 hex digest of the canonical manifest payload
  - ``_signature_key_id``: first 8 hex chars of SHA-256 of the signing key

Usage:
  python3 scripts/manage_skill_packages.py sign [--signed-by NAME] [--dev-key]
  python3 scripts/manage_skill_packages.py verify [--dev-mode] [--dev-key]
  python3 scripts/manage_skill_packages.py list
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow importing signing.py from the same directory
sys.path.insert(0, str(Path(__file__).resolve().parent))
from signing import (  # noqa: E402
    SigningKey,
    SigningError,
    VerificationError,
    sign_manifest,
    verify_manifest,
    verify_manifest_devmode,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = PROJECT_ROOT / "skill-packages"
SKILLS_DIR = PROJECT_ROOT / "skills"
CHECKSUMS_FILE = PACKAGES_DIR / "checksums.json"

MANIFEST_VERSION = "3.0"  # Incremented from 2.0 to reflect HMAC-SHA256 signing


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _all_packages() -> dict[str, Path]:
    return {p.stem: p for p in sorted(PACKAGES_DIR.glob("*.skill"))}


def _stale(skill_id: str, pkg_path: Path) -> bool:
    skill_md = SKILLS_DIR / skill_id / "SKILL.md"
    if not skill_md.is_file():
        return False
    return skill_md.stat().st_mtime > pkg_path.stat().st_mtime


def _git_commit() -> tuple[str, bool]:
    """Return (commit_hash, is_dirty). Both empty/"" if git unavailable."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        dirty_output = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return commit, bool(dirty_output)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "", False


def _load_manifest() -> dict:
    """Load checksums.json; return empty dict if absent."""
    if not CHECKSUMS_FILE.is_file():
        return {}
    return json.loads(CHECKSUMS_FILE.read_text(encoding="utf-8"))


def _manifest_is_v2(manifest: dict) -> bool:
    """True if manifest has a _release block (Phase 6+).

    Accepts any manifest_version ≥ 2.0 to remain backward-compatible with
    Phase 6 (v2.0) manifests while we upgrade to v3.0.
    """
    release = manifest.get("_release", {})
    if "_release" not in manifest:
        return False
    mv = release.get("manifest_version", "")
    # Accept 2.0 or 3.0+
    try:
        return float(mv) >= 2.0
    except (TypeError, ValueError):
        return False


def _manifest_is_signed(manifest: dict) -> bool:
    """True if manifest contains a cryptographic signature."""
    return bool(manifest.get("_release", {}).get("_signature"))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _resolve_signing_key(args: argparse.Namespace) -> SigningKey | None:
    """Resolve the signing key from CLI flags or environment.

    Returns None if neither a key source nor --dev-key is provided
    (caller must decide whether to treat as fatal or warning).
    """
    key_file = getattr(args, "signing_key_file", None)
    dev_key = getattr(args, "dev_key", False)

    if key_file:
        return SigningKey.from_file(Path(key_file))
    try:
        return SigningKey.best_available(dev_mode=dev_key)
    except SigningError:
        return None


def cmd_sign(args: argparse.Namespace) -> int:
    packages = _all_packages()
    if not packages:
        print("No .skill packages found in skill-packages/", file=sys.stderr)
        return 1

    # Resolve signing key
    key = _resolve_signing_key(args)
    if key is None:
        print(
            "[ERROR] No signing key available.  Pass --dev-key to auto-generate "
            "a local dev key, or set TRADERMONTY_SIGNING_KEY.",
            file=sys.stderr,
        )
        return 1

    commit, dirty = _git_commit()
    build_ts = datetime.now(timezone.utc).isoformat()

    release_meta = {
        "manifest_version": MANIFEST_VERSION,
        "build_timestamp": build_ts,
        "source_commit": commit,
        "source_dirty": dirty,
        "signed_by": getattr(args, "signed_by", None) or "unspecified",
        "signing_note": (
            "HMAC-SHA256 manifest signing enabled (Phase 1 — Third Hardening Pass). "
            "See docs/internal/key-management.md for production key requirements."
        ),
    }

    package_entries: dict[str, dict] = {}
    for skill_id, pkg_path in packages.items():
        package_entries[skill_id] = {
            "file": pkg_path.name,
            "sha256": _sha256(pkg_path),
            "size_bytes": pkg_path.stat().st_size,
            "stale": _stale(skill_id, pkg_path),
        }

    # Manifest layout: _release key first, then packages
    manifest = {"_release": release_meta, **package_entries}

    # Cryptographically sign the manifest
    signed = sign_manifest(manifest, key)

    CHECKSUMS_FILE.write_text(
        json.dumps(signed, indent=2) + "\n", encoding="utf-8"
    )

    stale_count = sum(1 for v in package_entries.values() if v["stale"])
    print(
        f"Signed {len(package_entries)} packages → "
        f"{CHECKSUMS_FILE.relative_to(PROJECT_ROOT)}"
    )
    print(f"  Build timestamp: {build_ts}")
    print(f"  Key ID:          {key.key_id}  (source: {key.source})")
    if commit:
        dirty_str = " (dirty)" if dirty else ""
        print(f"  Source commit:   {commit[:12]}{dirty_str}")
    if stale_count:
        print(
            f"  Note: {stale_count} package(s) are stale (SKILL.md newer than .skill file)."
            " Re-run packaging script to update, then re-sign."
        )
    return 0


def cmd_verify(args: argparse.Namespace | None = None) -> int:
    dev_mode = getattr(args, "dev_mode", False) if args else False

    if not CHECKSUMS_FILE.is_file():
        print(
            "checksums.json not found — run `python3 scripts/manage_skill_packages.py sign` first",
            file=sys.stderr,
        )
        return 1

    manifest = _load_manifest()
    packages = _all_packages()
    errors: list[str] = []
    warnings: list[str] = []
    ok_count = 0

    # --- Cryptographic signature check ---
    if dev_mode:
        key = _resolve_signing_key(args) if args else None
        if not verify_manifest_devmode(manifest, key):
            errors.append("Manifest signature verification failed in dev mode.")
    else:
        key = _resolve_signing_key(args) if args else None
        if key is None:
            # No key available — check if manifest is signed
            if _manifest_is_signed(manifest):
                errors.append(
                    "SIG_NOKEY  Manifest is signed but no verification key is available. "
                    "Set TRADERMONTY_SIGNING_KEY or pass --dev-key."
                )
            else:
                errors.append(
                    "SIG_MISSING  Manifest has no cryptographic signature. "
                    "Run `sign --dev-key` to sign the manifest, "
                    "or pass --dev-mode to accept unsigned manifests."
                )
        else:
            try:
                verify_manifest(manifest, key)
                print(
                    f"  Signature:   OK (key_id={manifest.get('_release', {}).get('_signature_key_id', '?')})"
                )
            except VerificationError as exc:
                errors.append(f"SIG_FAIL  {exc}")

    # --- Legacy manifest format warning ---
    if not _manifest_is_v2(manifest):
        warnings.append(
            "checksums.json uses the legacy v1 format (no _release metadata). "
            "Run `sign --dev-key` to upgrade to v3 with build provenance and signature."
        )

    # --- Package hash checks (skip _release key) ---
    for skill_id, entry in manifest.items():
        if skill_id == "_release":
            continue
        pkg_path = packages.get(skill_id)
        if pkg_path is None:
            errors.append(f"MISSING  {entry['file']} — recorded in checksums but file not found")
            continue
        actual = _sha256(pkg_path)
        if actual != entry["sha256"]:
            errors.append(
                f"CORRUPT  {entry['file']} — expected {entry['sha256'][:16]}…  got {actual[:16]}…"
            )
        else:
            ok_count += 1

    # --- New packages not in manifest ---
    for skill_id, pkg_path in packages.items():
        if skill_id not in manifest:
            errors.append(
                f"UNSIGNED {pkg_path.name} — not recorded in checksums.json (run sign)"
            )

    if warnings:
        for w in warnings:
            print(f"  WARN  {w}", file=sys.stderr)

    if errors:
        print(f"FAIL — {len(errors)} integrity issue(s):", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    stale = sum(
        1 for sid in manifest
        if sid != "_release" and sid in packages and _stale(sid, packages[sid])
    )
    print(f"OK — {ok_count} package(s) verified intact")
    if stale:
        print(f"  Warning: {stale} package(s) are stale relative to SKILL.md source")

    # Show provenance summary
    release = manifest.get("_release", {})
    if release:
        commit = release.get("source_commit", "")
        dirty = release.get("source_dirty", False)
        ts = release.get("build_timestamp", "unknown")
        print(f"  Built:  {ts}")
        if commit:
            print(f"  Commit: {commit[:12]}{'  (dirty at sign time)' if dirty else ''}")
    return 0


def cmd_list() -> int:
    packages = _all_packages()
    if not packages:
        print("No .skill packages found.")
        return 0

    manifest = _load_manifest()
    release = manifest.get("_release", {})

    if release:
        commit = release.get("source_commit", "")[:12] or "—"
        ts = release.get("build_timestamp", "—")
        signed_by = release.get("signed_by", "—")
        dirty = "  (dirty)" if release.get("source_dirty") else ""
        print(f"Manifest v{release.get('manifest_version', '?')}  |  Built: {ts}  |  Commit: {commit}{dirty}  |  Signed by: {signed_by}")
        print()

    print(f"{'SKILL':<45} {'SIZE':>8}  {'SHA-256 (16 chars)':>18}  {'STATUS'}")
    print("-" * 90)
    for skill_id, pkg_path in packages.items():
        size = pkg_path.stat().st_size
        recorded = manifest.get(skill_id, {})
        sha = recorded.get("sha256", "NOT SIGNED")[:16]
        status = "STALE" if _stale(skill_id, pkg_path) else "FRESH"
        signed = "✓" if skill_id in manifest else "✗"
        print(f"{skill_id:<45} {size:>8}  {sha:>18}  {signed} {status}")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _add_key_args(parser: argparse.ArgumentParser) -> None:
    """Add --dev-key and --signing-key-file to a subparser."""
    g = parser.add_mutually_exclusive_group()
    g.add_argument(
        "--dev-key",
        action="store_true",
        help=(
            "Use/auto-generate a local dev key at "
            "~/.config/tradermonty/dev-signing.key.  "
            "For local development only — not for distribution."
        ),
    )
    g.add_argument(
        "--signing-key-file",
        metavar="PATH",
        help="Path to a file containing a hex-encoded HMAC key.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage skill package checksums and integrity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_sign = sub.add_parser(
        "sign", help="Compute SHA-256, sign manifest, write checksums.json"
    )
    p_sign.add_argument(
        "--signed-by",
        default="unspecified",
        help="Name or identifier of the person/CI system running the sign command",
    )
    _add_key_args(p_sign)

    p_verify = sub.add_parser(
        "verify", help="Verify all packages against checksums.json (includes sig check)"
    )
    p_verify.add_argument(
        "--dev-mode",
        action="store_true",
        help=(
            "Accept unsigned manifests (with a warning) and skip hard failures "
            "when no key is available.  NOT for production."
        ),
    )
    _add_key_args(p_verify)

    sub.add_parser("list", help="List packages with size, hash, and staleness")

    args = parser.parse_args(argv)
    if args.command == "sign":
        return cmd_sign(args)
    elif args.command == "verify":
        return cmd_verify(args)
    elif args.command == "list":
        return cmd_list()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
