#!/usr/bin/env python3
"""Render maintenance LaunchAgents; --load explicitly activates their schedules."""

from __future__ import annotations

import argparse
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path
from xml.parsers.expat import ExpatError

LABELS = (
    "com.trade-analysis.skill-improvement",
    "com.trade-analysis.skill-generation-daily",
    "com.trade-analysis.skill-generation-weekly",
    "com.trade-analysis.skill-heartbeat",
)


def _expand(value, replacements):
    if isinstance(value, str):

        def replace(match):
            if match[0] not in replacements:
                raise ValueError("Unknown placeholder in maintenance template")
            return replacements[match[0]]

        # One pass: literal placeholder-like text in actual paths is preserved.
        return re.sub(r"\$[A-Z_]+", replace, value)
    if isinstance(value, list):
        return [_expand(v, replacements) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v, replacements) for k, v in value.items()}
    return value


def install(root, output, home, *, load=False):
    """Preflight every template/destination; preserve existing local customizations."""
    if load and sys.platform != "darwin":
        raise ValueError("--load requires macOS and a logged-in GUI session")
    root, output, home = (Path(p).resolve() for p in (root, output, home))
    rendered = []
    for label in LABELS:
        source = root / "launchd" / f"{label}.plist"
        try:
            data = plistlib.loads(source.read_bytes())
            data = _expand(data, {"$HOME": str(home), "$PROJECT_DIR": str(root)})
        except (OSError, ValueError, TypeError, ExpatError) as exc:
            raise ValueError(f"Invalid maintenance template: {source.name}") from exc
        if not isinstance(data, dict) or data.get("Label") != label:
            raise ValueError(f"Invalid template Label: {source.name}")
        if (
            not isinstance(data.get("ProgramArguments"), list)
            or not data["ProgramArguments"]
            or not all(isinstance(arg, str) for arg in data["ProgramArguments"])
            or data.get("WorkingDirectory") != str(root)
            or not all(
                isinstance(data.get(key), str) for key in ("StandardOutPath", "StandardErrorPath")
            )
        ):
            raise ValueError(f"Invalid maintenance template fields: {source.name}")
        target = output / source.name
        if target.is_symlink():
            raise ValueError(
                f"Refusing existing symlink: {target.name}; preserve it before installing"
            )
        if target.exists():
            try:
                existing = plistlib.loads(target.read_bytes())
            except (OSError, ValueError, TypeError, ExpatError):
                existing = None
            if existing != data:
                raise ValueError(
                    f"Refusing existing customized plist: {target.name}. "
                    "Unload that agent with launchctl bootout, move its plist aside, "
                    "then rerun the installer; preserve any local settings."
                )
        rendered.append((target, data))

    # No directories/files or jobs are changed until all conflicts are checked.
    output.mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    for target, data in rendered:
        if not target.exists():
            with target.open("xb") as stream:
                plistlib.dump(data, stream)
    if load:
        for target, data in rendered:
            try:
                subprocess.run(
                    ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(target)],
                    check=True,
                    capture_output=True,
                    timeout=15,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise ValueError(
                    f"Could not bootstrap {data['Label']}. Previously loaded agents are not stopped. "
                    "Inspect launchctl print; if updating, use launchctl bootout for that exact "
                    "service before rerunning --load. Earlier agents may already be loaded."
                ) from exc
    return [target for target, _ in rendered]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, default=Path.home() / "Library/LaunchAgents")
    parser.add_argument(
        "--load", action="store_true", help="Bootstrap the four schedules in your GUI domain"
    )
    args = parser.parse_args()
    try:
        paths = install(args.project_root, args.output_dir, Path.home(), load=args.load)
    except (OSError, ValueError) as exc:
        print(f"Installation failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"{len(paths)} maintenance plists ready; "
        + ("bootstrap succeeded." if args.load else "not loaded (use --load to activate).")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
