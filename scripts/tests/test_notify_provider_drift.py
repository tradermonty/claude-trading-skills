"""Offline notification lifecycle; all API calls are fake."""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from notify_provider_drift import NotificationError, notify, parse_report

REPO = "example/project"
RUN = f"https://github.com/{REPO}/actions/runs/123"


def report(code="wrong_type:volume:float", count=1):
    return {
        "provider": "fmp",
        "ok": False,
        "contracts": {
            "quote": {
                "ok": False,
                "status": 200,
                "rows": 1,
                "anomalies": [{"code": code, "severity": "fatal", "count": count}],
                "deprecations": [],
            }
        },
    }


class API:
    def __init__(self):
        self.issues = []
        self.comments = []
        self.calls = []
        self.fail = None

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path, copy.deepcopy(payload)))
        if self.fail == method:
            self.fail = None
            raise NotificationError("simulated API failure")
        if method == "GET" and path == f"repos/{REPO}":
            return {"owner": {"type": "User", "login": "example"}}
        if method == "GET" and "/comments?" in path:
            return copy.deepcopy(self.comments) if "page=1&" in path else []
        if method == "GET":
            return copy.deepcopy(self.issues) if "page=1&" in path else []
        if method == "POST" and path.endswith("/comments"):
            self.comments.append({"body": payload["body"]})
            return {}
        if method == "POST":
            item = {"number": len(self.issues) + 1, "state": "open", **payload}
            self.issues.append(item)
            return item
        if method == "PATCH":
            self.issues[0].update(payload)
            return self.issues[0]
        raise AssertionError((method, path, payload))


def test_create_assign_preserve_notes_and_repeat_idempotently():
    api = API()
    notify(report(), REPO, RUN, api)
    assert len(api.issues) == 1
    assert api.issues[0]["assignees"] == ["example"]
    api.issues[0]["body"] += "\nHuman notes: keep me."
    api.calls.clear()
    notify(report(), REPO, RUN, api)
    assert all(m == "GET" for m, _, _ in api.calls)
    assert not api.comments
    notify(report(count=2), REPO, RUN[:-3] + "124", api)
    assert len(api.comments) == 1
    assert api.issues[0]["body"].endswith("Human notes: keep me.")
    assert "Occurrences: 2" in api.issues[0]["body"]


def test_manual_close_same_run_and_reopen_new_run():
    api = API()
    notify(report(), REPO, RUN, api)
    api.issues[0]["state"] = "closed"
    notify(report(), REPO, RUN, api)
    assert api.issues[0]["state"] == "closed"
    notify(report(), REPO, RUN + "4", api)
    assert api.issues[0]["state"] == "open"
    assert len(api.comments) == 1


def test_retry_patch_failure_does_not_duplicate_comment():
    api = API()
    notify(report(), REPO, RUN, api)
    api.fail = "PATCH"
    with pytest.raises(NotificationError):
        notify(report(), REPO, RUN + "4", api)
    assert len(api.comments) == 1
    notify(report(), REPO, RUN + "4", api)
    assert len(api.comments) == 1
    api.fail = "POST"
    before = api.issues[0]["body"]
    with pytest.raises(NotificationError):
        notify(report(), REPO, RUN + "5", api)
    assert api.issues[0]["body"] == before


def test_duplicate_markers_fail_before_write_and_prs_ignored():
    api = API()
    notify(report(), REPO, RUN, api)
    api.issues.append({**api.issues[0], "number": 2, "pull_request": {}})
    notify(report(), REPO, RUN, api)
    del api.issues[1]["pull_request"]
    api.calls.clear()
    with pytest.raises(NotificationError):
        notify(report(), REPO, RUN, api)
    assert all(m == "GET" for m, _, _ in api.calls)


def test_healthy_and_warning_reports_need_no_api():
    data = report()
    data["ok"] = data["contracts"]["quote"]["ok"] = True
    data["contracts"]["quote"]["anomalies"] = []
    data["contracts"]["quote"]["deprecations"] = [
        {"code": "legacy_alias_present:x", "severity": "deprecation", "count": 1}
    ]
    api = API()
    notify(data, REPO, RUN, api)
    assert api.calls == []


@pytest.mark.parametrize(
    "code", ["@someone", "https://evil.test", "line\nbreak", "x`y", "", "a" * 257]
)
def test_unsafe_report_rejected_without_api(code):
    api = API()
    with pytest.raises(NotificationError):
        notify(report(code), REPO, RUN, api)
    assert not api.calls


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(provider="other"),
        lambda d: d.update(ok=True),
        lambda d: d["contracts"]["quote"].update(ok=True),
        lambda d: d["contracts"]["quote"]["anomalies"][0].update(count=True),
        lambda d: d["contracts"]["quote"]["anomalies"][0].update(severity="warning"),
        lambda d: d.update(contracts={}),
    ],
)
def test_invalid_reports_fail_before_api(mutate):
    data = report()
    mutate(data)
    api = API()
    with pytest.raises(NotificationError):
        notify(data, REPO, RUN, api)
    assert not api.calls


@pytest.mark.parametrize(
    "repo,url",
    [
        ("example/..", RUN),
        (REPO, RUN + "?x=1"),
        (REPO, RUN.replace("github.com", "evil.test")),
        ("other/project", RUN),
    ],
)
def test_destination_validation(repo, url):
    api = API()
    with pytest.raises(NotificationError):
        notify(report(), repo, url, api)
    assert not api.calls


def test_dedupe_and_sort():
    data = report()
    data["contracts"]["quote"]["anomalies"] *= 2
    assert parse_report(data) == [("quote", "wrong_type:volume:float", 2)]


def test_unsupported_owner_is_visible_failure():
    api = API()

    def org(method, path, payload=None):
        if path == f"repos/{REPO}":
            return {"owner": {"type": "Organization", "login": "example"}}
        return api(method, path, payload)

    with pytest.raises(NotificationError):
        notify(report(), REPO, RUN, org)
    assert not api.issues


def test_pagination_for_issues_and_comments():
    api = API()
    notify(report(), REPO, RUN, api)
    tracked = copy.deepcopy(api.issues)

    def paged(method, path, payload=None):
        if method == "GET" and "/issues?" in path:
            if "page=1&" in path:
                return [
                    {"number": n + 10, "body": "unrelated", "state": "open"} for n in range(100)
                ]
            return tracked
        if method == "GET" and "/comments?" in path and "page=1&" in path:
            return [{"body": "human"} for _ in range(100)]
        return api(method, path, payload)

    notify(report(), REPO, RUN + "4", paged)
    assert len(api.comments) == 1


def test_cli_readonly_and_apply_with_fake_gh(tmp_path):
    script = Path(__file__).resolve().parents[1] / "notify_provider_drift.py"
    data = tmp_path / "report.json"
    data.write_text(json.dumps(report()))
    env = {**os.environ, "PATH": "", "GITHUB_REPOSITORY": REPO, "GITHUB_RUN_ID": "123"}
    env.pop("GH_TOKEN", None)
    args = [sys.executable, str(script), "--report", str(data)]
    dry = subprocess.run(args, env=env, capture_output=True, text=True)
    assert dry.returncode == 0, dry.stderr
    log = tmp_path / "calls.jsonl"
    gh = tmp_path / "gh"
    gh.write_text(f"""#!{sys.executable}
import json, sys
from pathlib import Path
args = sys.argv[1:]
payload = json.load(sys.stdin) if "--input" in args else None
with Path({str(log)!r}).open("a") as out:
    out.write(json.dumps([args, payload]) + "\\n")
path = args[args.index("--method") + 2]
if "--method" in args and args[args.index("--method") + 1] == "POST":
    print(json.dumps({{"number": 1}}))
elif path.endswith("/project"):
    print(json.dumps({{"owner": {{"type": "User", "login": "example"}}}}))
else:
    print("[]")
""")
    gh.chmod(0o755)
    env.update(PATH=str(tmp_path), GH_TOKEN="fixture-token")
    live = subprocess.run([*args, "--apply"], env=env, capture_output=True, text=True)
    assert live.returncode == 0, live.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(calls) == 3
    assert all(c[0][:3] == ["api", "--hostname", "github.com"] for c in calls)
    assert "fixture-token" not in log.read_text() + live.stdout + live.stderr
    gh.write_text(
        f'#!{sys.executable}\nimport sys\nprint("fixture-token", file=sys.stderr)\nsys.exit(1)\n'
    )
    bad = subprocess.run([*args, "--apply"], env=env, capture_output=True, text=True)
    assert bad.returncode != 0
    assert "fixture-token" not in bad.stdout + bad.stderr


def test_rerunning_older_execution_cannot_regress_or_reopen():
    api = API()
    notify(report(), REPO, RUN, api)
    notify(report(), REPO, RUN + "4", api)
    api.issues[0]["state"] = "closed"
    before = api.issues[0]["body"]
    api.calls.clear()
    notify(report(), REPO, RUN, api)
    assert api.issues[0]["state"] == "closed"
    assert api.issues[0]["body"] == before
    assert len(api.comments) == 1
    assert all(method == "GET" for method, _, _ in api.calls)


def test_all_tracking_regions_validated_before_first_write():
    api = API()
    data = report()
    data["contracts"]["zquote"] = copy.deepcopy(data["contracts"]["quote"])
    notify(data, REPO, RUN, api)
    api.issues[1]["body"] = api.issues[1]["body"].replace("Latest run:", "Broken:")
    api.calls.clear()
    with pytest.raises(NotificationError):
        notify(data, REPO, RUN + "4", api)
    assert all(method == "GET" for method, _, _ in api.calls)


def test_comment_marker_on_second_page_avoids_duplicate_after_failed_patch():
    api = API()
    notify(report(), REPO, RUN, api)
    api.fail = "PATCH"
    with pytest.raises(NotificationError):
        notify(report(), REPO, RUN + "4", api)

    def paged(method, path, payload=None):
        if method == "GET" and "/comments?" in path:
            if "page=1&" in path:
                return [{"body": "human"} for _ in range(100)]
            return api.comments
        return api(method, path, payload)

    notify(report(), REPO, RUN + "4", paged)
    assert len(api.comments) == 1
    assert RUN + "4" in api.issues[0]["body"]
