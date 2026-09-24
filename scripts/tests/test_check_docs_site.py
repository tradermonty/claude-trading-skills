"""Regression tests for the GitHub Pages source/build/link gate (Issue #337)."""

from __future__ import annotations

import importlib.util
import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "check_docs_site.py"
SPEC = importlib.util.spec_from_file_location("check_docs_site", MODULE_PATH)
assert SPEC and SPEC.loader
docs_check = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = docs_check
SPEC.loader.exec_module(docs_check)

CONFIG = docs_check.SiteConfig(
    origin="https://tradermonty.github.io",
    baseurl="/claude-trading-skills",
)


def _write_page(path: Path, permalink: str, peer: str, *, title: str = "Page") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"title: {title!r}\n"
        f"permalink: {permalink!r}\n"
        f"lang_peer: {peer!r}\n"
        "summary: >-\n"
        "  a multiline value that must not confuse frontmatter parsing\n"
        "---\n"
        "# Page\n",
        encoding="utf-8",
    )


def _write_html(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"<!doctype html><html><body>{body}</body></html>", encoding="utf-8")


def _allowlist(path: Path, entries: list[dict[str, str]] | None = None) -> None:
    path.write_text(json.dumps({"schema_version": 1, "entries": entries or []}), encoding="utf-8")


def _public_resolver(*_args, **_kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def _response(status: int, *, location: str | None = None):
    headers = {} if location is None else {"Location": location}
    return docs_check.LinkResponse(status=status, headers=headers)


class FakeRequester:
    def __init__(self, responses: list[docs_check.LinkResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str, str, dict]] = []

    def __call__(self, method: str, url: str, pinned_ip: str, **kwargs):
        self.calls.append((method, url, pinned_ip, kwargs))
        if not self.responses:
            raise AssertionError("unexpected request")
        return self.responses.pop(0)


def test_source_accepts_quoted_multiline_frontmatter_and_reciprocal_peers(tmp_path):
    docs = tmp_path / "docs"
    _write_page(docs / "en" / "page.md", "/en/page/", "/ja/page/", title="A: title")
    _write_page(docs / "ja" / "page.md", "/ja/page/", "/en/page/", title="日本語")
    (docs / "vendor" / "gem").mkdir(parents=True)
    (docs / "vendor" / "gem" / "invalid.md").write_text(
        "---\npermalink: [invalid\n---\n", encoding="utf-8"
    )
    assert docs_check.validate_source(docs) == []


def test_source_rejects_duplicate_permalink_and_nonreciprocal_peer(tmp_path):
    docs = tmp_path / "docs"
    _write_page(docs / "en" / "a.md", "/en/a/", "/ja/a/")
    _write_page(docs / "en" / "duplicate.md", "/en/a/", "/ja/a/")
    _write_page(docs / "ja" / "a.md", "/ja/a/", "/en/other/")
    errors = docs_check.validate_source(docs)
    assert any("duplicate permalink" in error for error in errors)
    assert any("not reciprocal" in error for error in errors)


@pytest.mark.parametrize(
    "implicit_name",
    ["index.md", "index.markdown", "index.mkdown", "index.mkdn", "index.mkd", "index.html"],
)
def test_source_rejects_explicit_implicit_output_collision(tmp_path, implicit_name):
    docs = tmp_path / "docs"
    _write_page(docs / "explicit.md", "/foo/", "/ja/foo/")
    implicit = docs / "foo" / implicit_name
    implicit.parent.mkdir(parents=True)
    implicit.write_text("---\ntitle: implicit\n---\n", encoding="utf-8")
    errors = docs_check.validate_source(docs)
    assert any("conflicting Jekyll output 'foo/index.html'" in error for error in errors)


def test_source_rejects_duplicate_permalink_across_arbitrary_page_extensions(tmp_path):
    docs = tmp_path / "docs"
    for name in ("page.md", "page.mkd", "page.xhtml", "page.xml"):
        _write_page(docs / name, "/same/", "/ja/same/")
    errors = docs_check.validate_source(docs)
    assert sum("duplicate permalink '/same/'" in error for error in errors) == 3


def test_source_rejects_same_language_and_self_language_peers(tmp_path):
    docs = tmp_path / "docs"
    _write_page(docs / "en" / "a.md", "/en/a/", "/en/b/")
    _write_page(docs / "en" / "b.md", "/en/b/", "/en/a/")
    errors = docs_check.validate_source(docs)
    assert sum("must connect one /en/ page and one /ja/ page" in error for error in errors) == 2


@pytest.mark.parametrize(
    "content, expected",
    [
        ("---\npermalink: [bad\n---\n", "invalid frontmatter YAML"),
        ("---\n- not\n- a mapping\n---\n", "frontmatter must be a mapping"),
        ("---\npermalink: /a/\npermalink: /b/\n---\n", "duplicate key"),
        ("---\npermalink: 123\n---\n", "permalink must be a string"),
        ("---\npermalink: /a/\n", "no closing delimiter"),
    ],
)
def test_source_rejects_malformed_or_typed_frontmatter(tmp_path, content, expected):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "bad.md").write_text(content, encoding="utf-8")
    assert any(expected in error for error in docs_check.validate_source(docs))


def test_internal_checks_pages_assets_srcset_css_and_anchors(tmp_path):
    site = tmp_path / "site"
    _write_html(
        site / "index.html",
        """
        <a href="/claude-trading-skills/en/page/#target">page</a>
        <a href="https://tradermonty.github.io/claude-trading-skills/en/page/#target">absolute</a>
        <link href="/claude-trading-skills/assets/site.css" rel="stylesheet">
        <img src="/claude-trading-skills/assets/image.png"
             srcset="/claude-trading-skills/assets/image.png 1x, /claude-trading-skills/assets/image@2x.png 2x">
        <script src="/claude-trading-skills/assets/app.js"></script>
        <source src="/claude-trading-skills/assets/movie.mp4">
        <video src="/claude-trading-skills/assets/movie.mp4"
               poster="/claude-trading-skills/assets/poster.png"></video>
        <audio src="/claude-trading-skills/assets/sound.mp3"></audio>
        <iframe src="/claude-trading-skills/en/page/"></iframe>
        <object data="/claude-trading-skills/assets/icon.svg"></object>
        """,
    )
    _write_html(site / "en" / "page" / "index.html", '<h2 id="target">Target</h2>')
    assets = site / "assets"
    assets.mkdir()
    for name in (
        "image.png",
        "image@2x.png",
        "app.js",
        "movie.mp4",
        "poster.png",
        "sound.mp3",
        "icon.svg",
        "background.png",
    ):
        (assets / name).write_bytes(b"x")
    (assets / "site.css").write_text(
        "body { background: url('./background.png'); }", encoding="utf-8"
    )
    assert docs_check.validate_internal(site, CONFIG) == []


def test_internal_reports_missing_target_anchor_asset_and_traversal(tmp_path):
    site = tmp_path / "site"
    _write_html(
        site / "index.html",
        """
        <a href="/claude-trading-skills/missing/">missing</a>
        <a href="/claude-trading-skills/page/#missing">anchor</a>
        <img src="/claude-trading-skills/assets/missing.png">
        <script src="/claude-trading-skills/%2e%2e/secret.js"></script>
        """,
    )
    _write_html(site / "page" / "index.html", '<h2 id="present">Present</h2>')
    errors = docs_check.validate_internal(site, CONFIG)
    assert len(errors) == 4
    assert any("anchor #missing" in error for error in errors)
    assert any("path traversal" in error for error in errors)


def test_same_site_absolute_is_internal_and_excluded_from_external(tmp_path):
    site = tmp_path / "site"
    _write_html(
        site / "index.html",
        """
        <a href="https://tradermonty.github.io/claude-trading-skills/missing/">same</a>
        <a href="https://example.com/external#fragment">external</a>
        <a href="//cdn.example.com/asset">protocol relative</a>
        """,
    )
    errors = docs_check.validate_internal(site, CONFIG)
    assert len(errors) == 1
    assert "same" in errors[0]
    assert docs_check.collect_external_urls(site, CONFIG) == [
        "https://cdn.example.com/asset",
        "https://example.com/external",
    ]


def test_baseurl_rejects_root_relative_but_schedules_other_project_as_external(tmp_path):
    site = tmp_path / "site"
    _write_html(
        site / "index.html",
        """
        <a href="/en/page/">root-relative outside baseurl</a>
        <a href="https://tradermonty.github.io/en/page/">same-origin outside baseurl</a>
        """,
    )
    _write_html(site / "en" / "page" / "index.html", "<h1>Would otherwise pass</h1>")
    errors = docs_check.validate_internal(site, CONFIG)
    assert len(errors) == 1
    assert any("root-relative URL is outside configured baseurl" in error for error in errors)
    assert docs_check.collect_external_urls(site, CONFIG) == [
        "https://tradermonty.github.io/en/page/"
    ]


def test_validate_public_url_rejects_any_non_public_answer():
    def mixed_resolver(*_args, **_kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ]

    with pytest.raises(ValueError, match="non-public"):
        docs_check.validate_public_url("https://example.com", resolver=mixed_resolver)


def test_external_follows_only_safe_redirect_hops():
    requester = FakeRequester([_response(302, location="http://127.0.0.1/private")])

    def resolver(host, *_args, **_kwargs):
        address = "127.0.0.1" if host == "127.0.0.1" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]

    result = docs_check.check_url(
        "https://example.com/start",
        requester=requester,
        resolver=resolver,
        timeout=1,
        retries=0,
        max_redirects=2,
        max_bytes=8,
        sleep=lambda _seconds: None,
    )
    assert result["outcome"] == "failed"
    assert "non-public" in result["error"]
    assert len(requester.calls) == 1


def test_external_redirect_limit_and_transient_retry():
    redirects = [_response(302, location="/again"), _response(302, location="/again")]
    limited = docs_check.check_url(
        "https://example.com/start",
        requester=FakeRequester(redirects),
        resolver=_public_resolver,
        timeout=1,
        retries=0,
        max_redirects=1,
        max_bytes=8,
        sleep=lambda _seconds: None,
    )
    assert limited["outcome"] == "failed"
    assert "redirect limit" in limited["error"]

    retry_requester = FakeRequester([_response(503), _response(204)])
    retried = docs_check.check_url(
        "https://example.com",
        requester=retry_requester,
        resolver=_public_resolver,
        timeout=1,
        retries=1,
        max_redirects=1,
        max_bytes=8,
        sleep=lambda _seconds: None,
    )
    assert retried == {
        "attempts": 2,
        "final_url": "https://example.com",
        "outcome": "passed",
        "status": 204,
    }


def test_head_falls_back_to_bounded_get():
    requester = FakeRequester([_response(405), _response(200)])
    result = docs_check.check_url(
        "https://example.com",
        requester=requester,
        resolver=_public_resolver,
        timeout=1,
        retries=0,
        max_redirects=1,
        max_bytes=4,
        sleep=lambda _seconds: None,
    )
    assert result["outcome"] == "passed"
    assert [call[0] for call in requester.calls] == ["HEAD", "GET"]
    assert requester.calls[1][3]["max_bytes"] == 4


def test_validated_address_is_pinned_into_transport_despite_rebinding():
    requester = FakeRequester([_response(200)])

    def validation_resolver(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    result = docs_check.check_url(
        "https://rebind.example/path",
        requester=requester,
        resolver=validation_resolver,
        timeout=1,
        retries=0,
        max_redirects=1,
        max_bytes=8,
        sleep=lambda _seconds: None,
    )
    assert result["outcome"] == "passed"
    assert requester.calls[0][1:3] == (
        "https://rebind.example/path",
        "93.184.216.34",
    )


def test_pinned_https_socket_preserves_original_sni(monkeypatch):
    calls = {}
    raw_socket = object()
    wrapped_socket = object()

    def fake_create_connection(endpoint, timeout, source_address):
        calls["connect"] = (endpoint, timeout, source_address)
        return raw_socket

    class FakeContext:
        def wrap_socket(self, sock, *, server_hostname):
            calls["tls"] = (sock, server_hostname)
            return wrapped_socket

    connection = object.__new__(docs_check._PinnedHTTPSConnection)
    connection._pinned_ip = "93.184.216.34"
    connection.host = "rebind.example"
    connection.port = 443
    connection.timeout = 2
    connection.source_address = None
    connection._context = FakeContext()
    monkeypatch.setattr(docs_check.socket, "create_connection", fake_create_connection)
    connection.connect()

    assert calls["connect"] == (("93.184.216.34", 443), 2, None)
    assert calls["tls"] == (raw_socket, "rebind.example")
    assert connection.sock is wrapped_socket


def test_pinned_get_limits_response_read(monkeypatch):
    calls = {}

    class FakeBody:
        status = 200
        headers = {"Content-Type": "text/plain"}

        def read(self, size):
            calls["read"] = size
            return b"x" * size

    class FakeConnection:
        def __init__(self, host, pinned_ip, port, *, timeout):
            calls["init"] = (host, pinned_ip, port, timeout)

        def request(self, method, target, *, headers):
            calls["request"] = (method, target, headers)

        def getresponse(self):
            return FakeBody()

        def close(self):
            calls["closed"] = True

    monkeypatch.setattr(docs_check, "_PinnedHTTPConnection", FakeConnection)
    response = docs_check._request_pinned(
        "GET",
        "http://example.com/path?q=1#fragment",
        "93.184.216.34",
        timeout=3,
        max_bytes=4,
    )

    assert response.status == 200
    assert calls["init"] == ("example.com", "93.184.216.34", 80, 3)
    assert calls["request"][0:2] == ("GET", "/path?q=1")
    assert calls["request"][2]["Range"] == "bytes=0-3"
    assert calls["read"] == 4
    assert calls["closed"] is True


def test_allowlist_requires_complete_unexpired_entries(tmp_path):
    path = tmp_path / "allowlist.json"
    _allowlist(
        path,
        [
            {
                "url": "https://example.com",
                "reason": "temporary outage",
                "owner": "docs-maintainers",
                "issue": "https://github.com/tradermonty/claude-trading-skills/issues/337",
                "expires_on": "2026-01-01",
            }
        ],
    )
    allowed, errors = docs_check.load_allowlist(path, today=datetime(2026, 9, 23).date())
    assert allowed == set()
    assert any("expired" in error for error in errors)


def test_external_uses_fresh_success_cache_without_network(tmp_path):
    site = tmp_path / "site"
    _write_html(site / "index.html", '<a href="https://example.com/path">external</a>')
    allowlist = tmp_path / "allowlist.json"
    _allowlist(allowlist)
    cache = tmp_path / "cache.json"
    cache.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": {
                    "https://example.com/path": {
                        "checked_at": "2026-09-23T11:00:00Z",
                        "final_url": "https://example.com/path",
                        "outcome": "passed",
                        "status": 200,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    report = tmp_path / "report.json"
    requester = FakeRequester([])
    errors = docs_check.validate_external(
        site,
        CONFIG,
        allowlist_path=allowlist,
        cache_path=cache,
        report_path=report,
        cache_ttl_hours=24,
        retries=0,
        timeout=1,
        max_redirects=1,
        max_bytes=8,
        now=datetime(2026, 9, 23, 12, tzinfo=timezone.utc),
        requester=requester,
        resolver=_public_resolver,
        sleep=lambda _seconds: None,
    )
    assert errors == []
    assert requester.calls == []
    assert json.loads(report.read_text())["summary"]["cached"] == 1


def test_docs_workflow_is_pinned_and_covers_issue_contract():
    workflow_path = ROOT / ".github" / "workflows" / "docs-site.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.load(workflow_text, Loader=yaml.BaseLoader)

    assert "pull_request" in workflow["on"]
    assert "paths" not in workflow["on"]["pull_request"]
    assert "schedule" in workflow["on"]
    assert "workflow_dispatch" in workflow["on"]
    assert "--strict_front_matter" in workflow_text
    assert "working-directory: docs" in workflow_text
    assert "docs/Gemfile.lock" in workflow_text
    assert "check_docs_site.py source" in workflow_text
    assert "check_docs_site.py allowlist" in workflow_text
    assert "check_docs_site.py internal" in workflow_text
    assert "check_docs_site.py external" in workflow_text
    assert (
        "if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'"
        in workflow_text
    )

    expected_actions = {
        "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",  # pragma: allowlist secret
        "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",  # pragma: allowlist secret
        "astral-sh/setup-uv": "bec219d24cd3e171d82865faccec33120bb574f4",  # pragma: allowlist secret
        "ruby/setup-ruby": "762794c140bbeda0f1224786aa33b4b46783a6c1",  # pragma: allowlist secret
        "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",  # pragma: allowlist secret
        "actions/download-artifact": "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",  # pragma: allowlist secret
        "actions/cache": "0057852bfaa89a56745cba8c7296529d2fc39830",  # pragma: allowlist secret
    }
    raw_uses = __import__("re").findall(r"uses:\s+([^\s#]+)", workflow_text)
    all_uses = []
    for raw_use in raw_uses:
        match = __import__("re").fullmatch(r"([^@\s]+)@([0-9a-f]{40})", raw_use)
        assert match is not None, f"action is not pinned to a full SHA: {raw_use}"
        all_uses.append(match.groups())
    observed: dict[str, set[str]] = {}
    for name, ref in all_uses:
        observed.setdefault(name, set()).add(ref)
    assert observed == {name: {sha} for name, sha in expected_actions.items()}

    config_text = (ROOT / "docs" / "_config.yml").read_text(encoding="utf-8")
    assert "just-the-docs/just-the-docs@2ed4c0af735e95af5c0dcf7a605b07d903005b4e" in config_text


def test_repository_external_allowlist_is_valid():
    path = ROOT / "config" / "docs-external-link-allowlist.json"
    assert docs_check.validate_allowlist(path, today=datetime(2026, 9, 23).date()) == []
