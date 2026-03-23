"""Subprocess runner for trading skills. Writes timestamped JSON to fixed cache paths."""
from __future__ import annotations

import datetime
import glob
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from config import SKILL_REGISTRY, SKILL_TIMEOUT


class SkillsRunner:
    def __init__(self, cache_dir: Path, skills_root: Path):
        self.cache_dir = cache_dir
        self.skills_root = skills_root
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def run_skill(self, skill_name: str) -> bool:
        """Run a skill subprocess and cache its JSON output. Returns True on success."""
        cfg = SKILL_REGISTRY.get(skill_name)
        if cfg is None:
            print(f"[runner] Unknown skill: {skill_name}", file=sys.stderr)
            return False
        if cfg.get("script") is None:
            return False  # SKILL.md-only skill, no standalone script

        script = self.skills_root / cfg["script"]
        args = [
            a.replace("{cache_dir}", str(self.cache_dir))
            for a in cfg.get("args", [])
        ]
        cmd = [sys.executable, str(script)] + args
        stdout_capture = cfg.get("stdout_capture", False)

        stderr_log = self.cache_dir / f"{skill_name}.stderr.log"
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=SKILL_TIMEOUT,
                env=self._subprocess_env(),
            )
        except subprocess.TimeoutExpired:
            stderr_log.write_text(f"Timeout after {SKILL_TIMEOUT}s")
            print(f"[runner] {skill_name}: timeout", file=sys.stderr)
            return False

        stderr_log.write_text(result.stderr or "")

        if result.returncode != 0:
            print(f"[runner] {skill_name}: failed (exit {result.returncode})", file=sys.stderr)
            return False

        if stdout_capture:
            # Skill writes JSON to stdout — save directly to fixed cache path
            fixed = self.cache_dir / f"{skill_name}.json"
            fixed.write_text(result.stdout)
            return True

        return self._promote_latest_output(skill_name, cfg.get("output_prefix", ""))

    def _promote_latest_output(self, skill_name: str, prefix: str) -> bool:
        """Find the most-recently-modified JSON matching prefix, rename to <skill>.json."""
        pattern = str(self.cache_dir / f"{prefix}*.json")
        matches = glob.glob(pattern)
        if not matches:
            return False
        # Sort by mtime (not alphabetically) to handle any timestamp format
        newest = max(matches, key=os.path.getmtime)
        fixed = self.cache_dir / f"{skill_name}.json"
        Path(newest).rename(fixed)
        return True

    def _subprocess_env(self) -> dict:
        """Build env dict with API keys injected."""
        from config import FMP_API_KEY, FINVIZ_API_KEY, ANTHROPIC_API_KEY
        env = os.environ.copy()
        if FMP_API_KEY:
            env["FMP_API_KEY"] = FMP_API_KEY
        if FINVIZ_API_KEY:
            env["FINVIZ_API_KEY"] = FINVIZ_API_KEY
        if ANTHROPIC_API_KEY:
            env["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
        return env

    def is_stale(self, skill_name: str) -> bool:
        """Return True if cache is missing or older than 2× cadence."""
        cache_file = self.cache_dir / f"{skill_name}.json"
        if not cache_file.exists():
            return True
        try:
            data = json.loads(cache_file.read_text())
            generated_at = data.get("generated_at")
            if not generated_at:
                return True
            then = datetime.datetime.fromisoformat(generated_at)
            cfg = SKILL_REGISTRY.get(skill_name, {})
            cadence_min = cfg.get("cadence_min") or 120
            threshold = datetime.timedelta(minutes=cadence_min * 2)
            return (datetime.datetime.utcnow() - then) > threshold
        except Exception:
            return True

    def load_cache(self, skill_name: str) -> Optional[dict]:
        """Load cached JSON for a skill, or None if missing."""
        cache_file = self.cache_dir / f"{skill_name}.json"
        if not cache_file.exists():
            return None
        try:
            return json.loads(cache_file.read_text())
        except Exception:
            return None
