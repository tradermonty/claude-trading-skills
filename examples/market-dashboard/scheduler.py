"""APScheduler job setup for market-dashboard skill cadences."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import SKILL_REGISTRY


def _market_is_open() -> bool:
    """Check if current ET time is within market hours (Mon-Fri 9:30-16:00)."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (t.hour == 9 and t.minute >= 30) or (10 <= t.hour < 16)


def _pre_market_window() -> bool:
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return False
    t = now.time()
    return 7 <= t.hour < 9 or (t.hour == 9 and t.minute < 30)


def _make_intraday_job(runner, skill_name: str):
    """Job function that only fires during market hours."""
    def job():
        if _market_is_open():
            runner.run_skill(skill_name)
    job.__name__ = f"run_{skill_name.replace('-', '_')}"
    return job


def _make_30min_ordered_job(runner, skill_name: str):
    """Job that runs sector-analyst first (for exposure-coach), then the target skill.
    sector-analyst has no independent scheduled job; it only runs here as a prerequisite."""
    def job():
        if _market_is_open():
            if skill_name == "exposure-coach":
                # sector-analyst must run before exposure-coach
                runner.run_skill("sector-analyst")
            runner.run_skill(skill_name)
    job.__name__ = f"run_{skill_name.replace('-', '_')}"
    return job


def _make_open_once_job(runner, skill_name: str, cache_dir: Path):
    """Job that only runs once at open — checks cache's generated_at date to survive restarts."""
    def job():
        from zoneinfo import ZoneInfo
        if not _market_is_open():
            return
        today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
        cache_file = cache_dir / f"{skill_name}.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text())
                cached_date = data.get("generated_at", "")[:10]
                if cached_date == today:
                    return  # Already ran today — skip even after restart
            except Exception:
                pass
        runner.run_skill(skill_name)
    job.__name__ = f"run_{skill_name.replace('-', '_')}_at_open"
    return job


def _make_pre_market_job(runner, skill_name: str):
    """Job that fires once at 7 AM (pre-market window)."""
    def job():
        runner.run_skill(skill_name)
    job.__name__ = f"run_{skill_name.replace('-', '_')}_premarket"
    return job


def create_scheduler(
    runner,
    cache_dir: Path,
    pivot_monitor=None,
    pattern_extractor=None,
    ibkr_client=None,
    settings_manager=None,
    universe_builder=None,
    finnhub_api_key: str = "",
    fmp_api_key: str = "",
) -> AsyncIOScheduler:
    """Build and return a configured AsyncIOScheduler (not yet started).

    Note: sector-analyst has no independent scheduled job. It runs only as a
    prerequisite inside the exposure-coach 30-min job to guarantee execution order.
    """
    sched = AsyncIOScheduler(timezone="America/New_York")

    for skill_name, cfg in SKILL_REGISTRY.items():
        if cfg.get("script") is None:
            continue  # Skip SKILL.md-only skills
        if skill_name == "sector-analyst":
            continue  # Runs as dependency inside exposure-coach job only

        cadence = cfg.get("cadence_min")
        at_open = cfg.get("at_open_once", False)
        pre_market = cfg.get("pre_market_once", False)
        daily_6am = cfg.get("daily_6am", False)
        weekly_sunday = cfg.get("weekly_sunday", False)
        post_market_mwf = cfg.get("post_market_mwf", False)

        if at_open:
            sched.add_job(
                _make_open_once_job(runner, skill_name, cache_dir),
                CronTrigger(day_of_week="mon-fri", hour=9, minute=32),
                id=skill_name,
                replace_existing=True,
            )
        elif pre_market:
            sched.add_job(
                _make_pre_market_job(runner, skill_name),
                CronTrigger(day_of_week="mon-fri", hour=7, minute=0),
                id=skill_name,
                replace_existing=True,
            )
        elif daily_6am:
            sched.add_job(
                lambda sn=skill_name: runner.run_skill(sn) if runner else None,
                CronTrigger(day_of_week="mon-fri", hour=6, minute=0),
                id=skill_name,
                replace_existing=True,
            )
        elif weekly_sunday:
            sched.add_job(
                lambda sn=skill_name: runner.run_skill(sn) if runner else None,
                CronTrigger(day_of_week="sun", hour=18, minute=0),
                id=skill_name,
                replace_existing=True,
            )
        elif post_market_mwf:
            sched.add_job(
                lambda sn=skill_name: runner.run_skill(sn) if runner else None,
                CronTrigger(day_of_week="mon,wed,fri", hour=16, minute=15),
                id=skill_name,
                replace_existing=True,
            )
        elif cadence:
            if cadence <= 60:
                sched.add_job(
                    _make_30min_ordered_job(runner, skill_name),
                    IntervalTrigger(minutes=cadence),
                    id=skill_name,
                    replace_existing=True,
                )
            else:
                sched.add_job(
                    _make_intraday_job(runner, skill_name),
                    IntervalTrigger(minutes=cadence),
                    id=skill_name,
                    replace_existing=True,
                )

    # ── Plan 3: Pivot monitor jobs ────────────────────────────────────────
    if pivot_monitor is not None:
        def stage1_job():
            candidates = pivot_monitor.load_candidates()
            tagged = pivot_monitor.run_stage1_check(candidates)
            with pivot_monitor._lock:
                pivot_monitor._candidates = tagged

        sched.add_job(
            stage1_job,
            CronTrigger(day_of_week="mon-fri", hour=7, minute=0),
            id="pivot_stage1",
            replace_existing=True,
        )

        async def monitor_start_job():
            settings = pivot_monitor._settings.load()
            if settings.get("mode") != "auto":
                return
            if not pivot_monitor._candidates:
                pivot_monitor._candidates = pivot_monitor.run_stage1_check(
                    pivot_monitor.load_candidates()
                )
            asyncio.create_task(pivot_monitor.start(pivot_monitor._candidates))

        sched.add_job(
            monitor_start_job,
            CronTrigger(day_of_week="mon-fri", hour=9, minute=32),
            id="pivot_monitor_start",
            replace_existing=True,
        )

        sched.add_job(
            lambda: pivot_monitor._check_exit_management(),
            IntervalTrigger(minutes=5),
            id="exit_management",
            replace_existing=True,
        )

    if pattern_extractor is not None:
        sched.add_job(
            pattern_extractor.extract,
            CronTrigger(day_of_week="sat", hour=18, minute=0),
            id="pattern_extraction",
            replace_existing=True,
        )

    # ── Weekly universe builder for non-US markets ─────────────────────────
    if ibkr_client is not None and settings_manager is not None:
        from universe_builder import UniverseBuilder
        universe_builder = UniverseBuilder(
            ibkr_client=ibkr_client,
            cache_dir=cache_dir,
            request_delay=6.0,
        )

        def universe_build_job():
            markets = settings_manager.get_enabled_markets()
            universe_builder.build_all(markets)

        sched.add_job(
            universe_build_job,
            CronTrigger(day_of_week="sun", hour=20, minute=0),
            id="universe_builder",
            replace_existing=True,
        )

    # ── Universe builder jobs ──────────────────────────────────────────────────
    if universe_builder is not None:
        sched.add_job(
            lambda: universe_builder.build_queue(finnhub_api_key=finnhub_api_key),
            CronTrigger(day_of_week="sun", hour=18, minute=0),
            id="universe_build_queue",
            replace_existing=True,
        )
        sched.add_job(
            lambda: universe_builder.run_nightly_batch(
                fmp_api_key=fmp_api_key,
                batch_size=20,
            ),
            CronTrigger(day_of_week="mon-fri", hour=16, minute=30),
            id="universe_nightly_batch",
            replace_existing=True,
        )

    return sched
