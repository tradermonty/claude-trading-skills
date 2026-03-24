# tests/test_scheduler.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_create_scheduler_returns_scheduler_instance():
    from scheduler import create_scheduler
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    sched = create_scheduler(runner=None, cache_dir=Path("/tmp/test_cache"))
    assert isinstance(sched, AsyncIOScheduler)
    assert not sched.running


def test_scheduler_registers_ftd_job():
    from scheduler import create_scheduler
    sched = create_scheduler(runner=None, cache_dir=Path("/tmp/test_cache"))
    job_ids = [j.id for j in sched.get_jobs()]
    assert "ftd-detector" in job_ids


def test_scheduler_registers_vcp_job():
    from scheduler import create_scheduler
    sched = create_scheduler(runner=None, cache_dir=Path("/tmp/test_cache"))
    job_ids = [j.id for j in sched.get_jobs()]
    assert "vcp-screener" in job_ids


def test_scheduler_registers_daily_6am_job():
    from scheduler import create_scheduler
    sched = create_scheduler(runner=None, cache_dir=Path("/tmp/test_cache"))
    job_ids = [j.id for j in sched.get_jobs()]
    assert "economic-calendar-fetcher" in job_ids


def test_scheduler_registers_weekly_sunday_job():
    from scheduler import create_scheduler
    sched = create_scheduler(runner=None, cache_dir=Path("/tmp/test_cache"))
    job_ids = [j.id for j in sched.get_jobs()]
    assert "institutional-flow-tracker" in job_ids


def test_sector_analyst_has_no_independent_job():
    """sector-analyst must NOT have its own independent interval job.
    It runs only as a prerequisite inside the exposure-coach job to guarantee ordering.
    A separate sector-analyst interval job would race with exposure-coach."""
    from scheduler import create_scheduler
    sched = create_scheduler(runner=None, cache_dir=Path("/tmp/test_cache"))
    job_ids = [j.id for j in sched.get_jobs()]
    assert "sector-analyst" not in job_ids, (
        "sector-analyst must not have an independent scheduler job; "
        "it runs as a dependency inside exposure-coach's job"
    )
    assert "exposure-coach" in job_ids


def test_exposure_coach_job_runs_sector_analyst_first(tmp_path):
    """The exposure-coach job function must call sector-analyst before exposure-coach."""
    from scheduler import create_scheduler
    from unittest.mock import MagicMock, call

    mock_runner = MagicMock()
    sched = create_scheduler(runner=mock_runner, cache_dir=tmp_path)
    jobs = {j.id: j for j in sched.get_jobs()}
    exposure_job = jobs["exposure-coach"]

    import scheduler as sched_module
    original = sched_module._market_is_open
    sched_module._market_is_open = lambda: True
    try:
        exposure_job.func()
    finally:
        sched_module._market_is_open = original

    calls = [c[0][0] for c in mock_runner.run_skill.call_args_list]
    assert calls[0] == "sector-analyst", f"First call must be sector-analyst, got {calls}"
    assert "exposure-coach" in calls


def test_scheduler_registers_stage1_job_when_pivot_monitor_given():
    from scheduler import create_scheduler
    from unittest.mock import MagicMock
    monitor = MagicMock()
    monitor.load_candidates.return_value = []
    sched = create_scheduler(runner=None, cache_dir=Path("/tmp"), pivot_monitor=monitor)
    job_ids = [j.id for j in sched.get_jobs()]
    assert "pivot_stage1" in job_ids


def test_scheduler_registers_monitor_start_job_when_pivot_monitor_given():
    from scheduler import create_scheduler
    from unittest.mock import MagicMock
    monitor = MagicMock()
    sched = create_scheduler(runner=None, cache_dir=Path("/tmp"), pivot_monitor=monitor)
    job_ids = [j.id for j in sched.get_jobs()]
    assert "pivot_monitor_start" in job_ids


def test_scheduler_registers_pattern_extraction_when_extractor_given():
    from scheduler import create_scheduler
    from unittest.mock import MagicMock
    extractor = MagicMock()
    sched = create_scheduler(runner=None, cache_dir=Path("/tmp"), pattern_extractor=extractor)
    job_ids = [j.id for j in sched.get_jobs()]
    assert "pattern_extraction" in job_ids


def test_scheduler_has_universe_build_queue_job():
    """Scheduler includes a Sunday 18:00 job for build_queue."""
    from scheduler import create_scheduler
    from unittest.mock import MagicMock
    from pathlib import Path
    import tempfile

    mock_runner = MagicMock()
    mock_universe_builder = MagicMock()
    cache_dir = Path(tempfile.mkdtemp())

    sched = create_scheduler(
        runner=mock_runner,
        cache_dir=cache_dir,
        universe_builder=mock_universe_builder,
        finnhub_api_key="test",
        fmp_api_key="test",
    )
    job_ids = [j.id for j in sched.get_jobs()]
    assert "universe_build_queue" in job_ids

    job = next(j for j in sched.get_jobs() if j.id == "universe_build_queue")
    job.func()
    mock_universe_builder.build_queue.assert_called_once_with(finnhub_api_key="test")


def test_scheduler_has_nightly_batch_job():
    """Scheduler includes a Mon-Fri 16:30 job for run_nightly_batch."""
    from scheduler import create_scheduler
    from unittest.mock import MagicMock
    from pathlib import Path
    import tempfile

    mock_runner = MagicMock()
    mock_universe_builder = MagicMock()
    cache_dir = Path(tempfile.mkdtemp())

    sched = create_scheduler(
        runner=mock_runner,
        cache_dir=cache_dir,
        universe_builder=mock_universe_builder,
        finnhub_api_key="test",
        fmp_api_key="test",
    )
    job_ids = [j.id for j in sched.get_jobs()]
    assert "universe_nightly_batch" in job_ids

    job = next(j for j in sched.get_jobs() if j.id == "universe_nightly_batch")
    job.func()
    mock_universe_builder.run_nightly_batch.assert_called_once_with(fmp_api_key="test", batch_size=20)
