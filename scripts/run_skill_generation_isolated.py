#!/usr/bin/env python3
"""Run generation in a dedicated, non-destructively synchronized POSIX clone."""

from __future__ import annotations

import argparse
import configparser
import os
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from urllib.parse import urlsplit

try:
    import fcntl
except ImportError:  # launchd/POSIX entry point; importing on Windows remains safe.
    fcntl = None


class LaunchError(ValueError):
    """Unsafe or incomplete automation setup; preserve it for local recovery."""


def overlaps(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def origin_from(primary: Path) -> str:
    """Read origin metadata without running Git in the primary checkout."""
    gitdir = primary / ".git"
    if gitdir.is_file():
        value = gitdir.read_text().strip()
        if not value.startswith("gitdir: "):
            raise LaunchError("Invalid primary Git directory metadata")
        gitdir = (primary / value[8:]).resolve()
    if (gitdir / "config.worktree").exists():
        raise LaunchError(
            "Primary worktree config is unsupported; use a self-contained origin config"
        )
    if (gitdir / "commondir").is_file():
        gitdir = (gitdir / (gitdir / "commondir").read_text().strip()).resolve()
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with (gitdir / "config").open() as stream:
            parser.read_file(stream)
        if any(
            section.lower().split()[0].split(".")[0] in {"include", "includeif"}
            for section in parser.sections()
        ):
            raise LaunchError(
                "Primary Git include settings are unsupported; use a self-contained origin config"
            )
        if parser.getboolean("extensions", "worktreeconfig", fallback=False):
            raise LaunchError(
                "Primary worktree config is unsupported; use a self-contained origin config"
            )
        origin = parser.get('remote "origin"', "url").strip()
    except (OSError, configparser.Error) as exc:
        raise LaunchError("Cannot read the primary origin configuration") from exc
    if not origin or origin.startswith("-"):
        raise LaunchError("Invalid origin configuration")
    try:
        embedded_credentials = (
            origin.startswith(("http://", "https://")) and urlsplit(origin).username is not None
        )
    except ValueError as exc:
        raise LaunchError("Invalid origin URL configuration") from exc
    if embedded_credentials:
        raise LaunchError("Use a credential helper instead of credentials in the origin URL")
    # Resolve filesystem origins relative to primary, not the bot's cwd.
    if ":" not in origin:
        local = (primary / origin).resolve()
        if overlaps(local, primary):
            raise LaunchError("A filesystem origin must be outside the primary checkout")
        origin = str(local)
    return origin


def git(checkout: Path, env: dict[str, str], *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=checkout,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LaunchError("Automation checkout Git operation could not complete") from exc
    if result.returncode:
        # Git stderr/command arguments can expose remote credentials or paths.
        raise LaunchError("Automation checkout Git operation failed; inspect it locally")
    return result.stdout.strip()


def validate_repo(checkout: Path, env: dict[str, str], origin: str) -> None:
    gitdir = checkout / ".git"
    if gitdir.is_symlink() or not gitdir.is_dir() or (gitdir / "commondir").exists():
        raise LaunchError("Generation requires an independent clone, not a linked Git directory")
    top = Path(git(checkout, env, "rev-parse", "--show-toplevel")).resolve()
    actual_git = Path(git(checkout, env, "rev-parse", "--absolute-git-dir")).resolve()
    common = (checkout / git(checkout, env, "rev-parse", "--git-common-dir")).resolve()
    if top != checkout or actual_git != gitdir or common != gitdir:
        raise LaunchError("Generation Git directories must stay within the dedicated checkout")
    if git(checkout, env, "config", "--get", "remote.origin.url") != origin:
        raise LaunchError("Generation checkout origin differs; recover it manually")
    # Compare effective URLs too: global config may inject another origin URL,
    # while normal insteadOf rewrites should still resolve consistently.
    expected_url = git(checkout, env, "ls-remote", "--get-url", origin)
    if git(checkout, env, "remote", "get-url", "origin") != expected_url:
        raise LaunchError("Effective generation origin differs; inspect Git configuration")
    if git(checkout, env, "ls-files", "--", "logs", "reports"):
        raise LaunchError("Tracked shared-output paths are not supported")


def share_outputs(primary: Path, checkout: Path) -> None:
    # Validate every destination before creating links; never remove user data.
    for name in ("logs", "reports"):
        target, link = primary / name, checkout / name
        if link.is_symlink():
            if link.resolve() != target.resolve():
                raise LaunchError("Unexpected shared-output link; preserve it for recovery")
        elif link.exists():
            raise LaunchError("Existing checkout output data requires manual migration")
        if target.exists() and not target.is_dir():
            raise LaunchError("Primary output location is not a directory")
    exclude = checkout / ".git/info/exclude"
    if exclude.is_symlink() or not exclude.resolve().is_relative_to(checkout / ".git"):
        raise LaunchError("Unsafe clone-local exclude location")
    exclude.parent.mkdir(parents=True, exist_ok=True)
    current = exclude.read_text() if exclude.exists() else ""
    missing = [entry for entry in ("/logs", "/reports") if entry not in current.splitlines()]
    if missing:
        with exclude.open("a") as stream:
            stream.write(
                ("\n" if current and not current.endswith("\n") else "") + "\n".join(missing) + "\n"
            )
    for name in ("logs", "reports"):
        target, link = primary / name, checkout / name
        target.mkdir(parents=True, exist_ok=True)
        if not link.is_symlink():
            link.symlink_to(target, target_is_directory=True)


def launch(primary: Path, mode: str, dry_run: bool = False) -> int:
    if fcntl is None:
        raise LaunchError("Generation isolation requires a POSIX system with flock")
    if mode not in {"daily", "weekly"}:
        raise LaunchError("Generation mode must be daily or weekly")
    primary = primary.resolve()
    home = Path(os.environ.get("HOME", str(Path.home())))
    checkout = Path(
        os.environ.get(
            "SKILL_GENERATION_CHECKOUT",
            str(home / ".local/share/claude-trading-skills-generation-bot"),
        )
    ).resolve()
    improvement = Path(
        os.environ.get("SKILL_LOOP_CHECKOUT", str(home / ".local/share/claude-trading-skills-bot"))
    ).resolve()
    if overlaps(checkout, primary) or overlaps(checkout, improvement):
        raise LaunchError(
            "Generation checkout must be disjoint from primary and improvement checkouts"
        )
    origin = origin_from(primary)
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.pop("CLAUDECODE", None)
    env["PWD"] = str(checkout)
    (primary / "logs").mkdir(parents=True, exist_ok=True)
    checkout.parent.mkdir(parents=True, exist_ok=True)
    lock_paths = [
        primary / "logs/.skill_generation_launcher.lock",
        checkout.parent / f".{checkout.name}.generation.lock",
    ]
    with ExitStack() as stack:
        locks = []
        for path in sorted(lock_paths):
            if path.is_symlink():
                raise LaunchError("Refusing a symlinked generation lock")
            lock = stack.enter_context(path.open("a"))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("Generation launcher already active; skipping this invocation")
                return 0
            locks.append(lock)
        # No explicit LOCK_UN: inherited descriptors must retain exclusion if
        # only this helper dies while the pipeline child is still alive.
        if not checkout.exists():
            checkout.mkdir()
        if not (checkout / ".git").exists():
            if any(checkout.iterdir()):
                raise LaunchError("Nonempty generation directory is not a clone; preserve it")
            git(
                checkout,
                env,
                "-c",
                f"core.worktree={checkout}",
                "clone",
                "--branch",
                "main",
                "--single-branch",
                "--",
                origin,
                ".",
            )
        validate_repo(checkout, env, origin)
        share_outputs(primary, checkout)
        if git(checkout, env, "status", "--porcelain"):
            raise LaunchError("Generation checkout is dirty; preserve it and recover manually")
        if git(checkout, env, "branch", "--show-current") != "main":
            raise LaunchError("Generation checkout is off main; preserve it and recover manually")
        git(checkout, env, "fetch", "origin", "main", "--no-tags")
        if git(
            checkout, env, "ls-tree", "-r", "--name-only", "FETCH_HEAD", "--", "logs", "reports"
        ):
            raise LaunchError("Fetched main tracks shared output paths; refusing synchronization")
        # Refuse local unpublished commits as well as divergent histories. A
        # normal `merge --ff-only` alone accepts an ahead local main unchanged.
        git(checkout, env, "merge-base", "--is-ancestor", "HEAD", "FETCH_HEAD")
        git(checkout, env, "merge", "--ff-only", "FETCH_HEAD")
        if (
            git(checkout, env, "config", "--get", "branch.main.remote") != "origin"
            or git(checkout, env, "config", "--get", "branch.main.merge") != "refs/heads/main"
        ):
            raise LaunchError("Generation main must track origin/main")
        command = [
            sys.executable,
            str(checkout / "scripts/run_skill_generation_pipeline.py"),
            "--mode",
            mode,
        ]
        if dry_run:
            command.append("--dry-run")
        command += ["--project-root", str(checkout)]
        result = subprocess.run(
            command,
            cwd=checkout,
            env=env,
            pass_fds=tuple(lock.fileno() for lock in locks),
            check=False,
        )
        return result.returncode if result.returncode >= 0 else 128 - result.returncode


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("daily", "weekly"), required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        return launch(Path(__file__).resolve().parents[1], args.mode, args.dry_run)
    except (LaunchError, OSError, RuntimeError) as exc:
        message = (
            str(exc)
            if isinstance(exc, LaunchError)
            else "Generation setup failed; inspect local paths"
        )
        print(f"Error: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
