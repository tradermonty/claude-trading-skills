from datetime import date, datetime, timezone

from app import readers


def test_parse_stamp_with_and_without_time():
    assert readers.parse_stamp("exposure_posture_2026-11-18_211500.json") == datetime(
        2026, 11, 18, 21, 15, 0
    )
    assert readers.parse_stamp("weekly_digest_2026-11-16.json") == datetime(2026, 11, 16)
    assert readers.parse_stamp("notes.json") is None


def test_list_reports_newest_first_and_prefix_exact(reports_dir):
    files = readers.list_reports(reports_dir, "exposure")
    names = [p.name for p in files]
    assert names[0] == "exposure_posture_2026-11-18_211500.json"
    assert all(n.startswith("exposure_posture_") and n.endswith(".json") for n in names)
    assert len(names) == 4


def test_latest_returns_data_and_md_sibling(reports_dir):
    latest = readers.latest(reports_dir, "exposure")
    assert latest["data"]["exposure_ceiling_pct"] == 50
    assert latest["md_name"] == "exposure_posture_2026-11-18_211500.md"


def test_latest_missing_type_is_none(reports_dir):
    assert readers.latest(reports_dir, "digest") is None


def test_latest_on_missing_dir(tmp_path):
    assert readers.latest(tmp_path / "nope", "exposure") is None


def test_history_one_point_per_day_oldest_first(reports_dir):
    hist = readers.history(reports_dir, "exposure")
    assert hist == [("2026-11-16", 60), ("2026-11-17", 70), ("2026-11-18", 50)]


def test_history_nested_value(reports_dir):
    assert readers.history(reports_dir, "breadth") == [("2026-11-18", 55.5)]


def test_age_hours():
    now = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
    stamp = datetime(2026, 11, 18, 12, 0)
    assert readers.age_hours(stamp, now) == 24


def test_load_theses_skips_bad_files(state_dir):
    theses, errors = readers.load_theses(state_dir)
    assert [t["ticker"] for t in theses] == ["AAA", "BBB", "CCC"]
    assert errors == ["th_bad.yaml"]


def test_thesis_summary(state_dir):
    theses, _ = readers.load_theses(state_dir)
    s = readers.thesis_summary(theses, today=date(2026, 11, 18))
    assert s["by_status"] == {"ACTIVE": 1, "IDEA": 1, "CLOSED": 1}
    # CLOSED is terminal, so its overdue review does not count.
    assert [t["ticker"] for t in s["review_due"]] == ["AAA"]
    assert s["open_risk_dollars"] == 6.0
    assert s["closed_pnl_dollars"] == -4.0


def test_find_thesis_and_journal(state_dir):
    theses, _ = readers.load_theses(state_dir)
    assert readers.find_thesis(theses, "th_ccc_1")["ticker"] == "CCC"
    assert readers.find_thesis(theses, "missing") is None
    assert "Stopped out" in readers.journal_for(state_dir, "th_ccc_1")
    assert readers.journal_for(state_dir, "th_aaa_1") is None


def test_safe_report_path_blocks_traversal(reports_dir):
    assert readers.safe_report_path(reports_dir, "exposure_posture_2026-11-18_211500.md")
    assert readers.safe_report_path(reports_dir, "../state/x.md") is None
    assert readers.safe_report_path(reports_dir, "/etc/passwd") is None
    assert readers.safe_report_path(reports_dir, "missing.md") is None


def test_safe_report_path_blocks_other_suffixes(reports_dir):
    (reports_dir / "secret.env").write_text("X=1")
    assert readers.safe_report_path(reports_dir, "secret.env") is None


def test_all_reports_groups_by_type(reports_dir):
    groups = readers.all_reports(reports_dir)
    assert groups["exposure"][0]["name"] == "exposure_posture_2026-11-18_211500.json"
    assert "vcp" in groups


def test_unstamped_files_with_same_prefix_are_ignored(reports_dir):
    # market-breadth-analyzer keeps a rolling market_breadth_history.json next to its reports.
    (reports_dir / "market_breadth_history.json").write_text('{"rows": []}')
    names = [p.name for p in readers.list_reports(reports_dir, "breadth")]
    assert names == ["market_breadth_2026-11-18_211000.json"]
    assert readers.latest(reports_dir, "breadth")["data"]["composite"]["zone"] == "Neutral"
