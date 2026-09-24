#!/usr/bin/env python3
"""Validate the Jekyll documentation source, built site, and external links.

The ``source``, ``allowlist``, and ``internal`` validators are offline;
``external`` is intended for the scheduled job and has pinned-address bounded
networking, an expiring allowlist, and a success-only cache.
"""

from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import posixpath
import re
import socket
import ssl
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urldefrag, urljoin, urlsplit, urlunsplit

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
TRANSIENT_STATUSES = {408, 425, 429, 500, 502, 503, 504}
HEAD_FALLBACK_STATUSES = {400, 403, 405, 501}
IGNORED_SCHEMES = {"data", "javascript", "mailto", "tel"}
IGNORED_SOURCE_ROOTS = {
    ".bundle",
    ".jekyll-cache",
    ".sass-cache",
    "_site",
    "internal",
    "node_modules",
    "vendor",
}
CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
MARKDOWN_SUFFIXES = {".markdown", ".mkdown", ".mkdn", ".mkd", ".md"}


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True)
class SiteConfig:
    origin: str
    baseurl: str


@dataclass(frozen=True)
class SourcePage:
    path: Path
    permalink: str | None
    lang_peer: str | None
    output_path: str


@dataclass(frozen=True)
class Reference:
    source_path: Path
    source_url: str
    raw_url: str
    attribute: str


@dataclass(frozen=True)
class LinkResponse:
    status: int
    headers: dict[str, str]


class LinkHTMLParser(HTMLParser):
    """Collect link-bearing HTML attributes and anchor names."""

    _SRC_TAGS = {"audio", "iframe", "img", "script", "source", "video"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[str, str]] = []
        self.anchors: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value for name, value in attrs if value is not None}
        anchor_id = values.get("id")
        if anchor_id:
            self.anchors.add(anchor_id)
        if tag == "a" and values.get("name"):
            self.anchors.add(values["name"])

        if tag in {"a", "link"} and values.get("href"):
            self.references.append((values["href"], f"{tag}[href]"))
        if tag in self._SRC_TAGS and values.get("src"):
            self.references.append((values["src"], f"{tag}[src]"))
        if tag in {"img", "source"} and values.get("srcset"):
            for candidate in _parse_srcset(values["srcset"]):
                self.references.append((candidate, f"{tag}[srcset]"))
        if tag == "video" and values.get("poster"):
            self.references.append((values["poster"], "video[poster]"))
        if tag == "object" and values.get("data"):
            self.references.append((values["data"], "object[data]"))


def _parse_srcset(value: str) -> list[str]:
    if value.lstrip().lower().startswith("data:"):
        return []
    candidates: list[str] = []
    for item in value.split(","):
        fields = item.strip().split()
        if fields and not fields[0].lower().startswith("data:"):
            candidates.append(fields[0])
    return candidates


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return value


def load_site_config(path: Path) -> SiteConfig:
    raw = _load_yaml_mapping(path)
    origin = raw.get("url")
    baseurl = raw.get("baseurl", "")
    if not isinstance(origin, str) or not origin:
        raise ValueError(f"{path}: url must be a non-empty string")
    split = urlsplit(origin)
    if split.scheme not in {"http", "https"} or not split.netloc or split.path not in {"", "/"}:
        raise ValueError(f"{path}: url must be an HTTP(S) origin without a path")
    if not isinstance(baseurl, str):
        raise ValueError(f"{path}: baseurl must be a string")
    baseurl = baseurl.rstrip("/")
    if baseurl and not baseurl.startswith("/"):
        raise ValueError(f"{path}: baseurl must be empty or start with /")
    return SiteConfig(origin=f"{split.scheme.lower()}://{split.netloc.lower()}", baseurl=baseurl)


def _canonical_site_path(value: str, *, field: str, source: Path) -> str:
    split = urlsplit(value)
    if (
        split.scheme
        or split.netloc
        or split.query
        or split.fragment
        or not split.path.startswith("/")
    ):
        raise ValueError(f"{source}: {field} must be an absolute site path: {value!r}")
    decoded = unquote(split.path)
    if any(part == ".." for part in PurePosixPath(decoded).parts):
        raise ValueError(f"{source}: {field} contains parent traversal: {value!r}")
    trailing = decoded.endswith("/")
    normalized = posixpath.normpath(decoded)
    if normalized == ".":
        normalized = "/"
    if trailing and normalized != "/":
        normalized += "/"
    return normalized


def _frontmatter(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"{path}: cannot read source page: {exc}") from exc
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    closing = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() in {"---", "..."}),
        None,
    )
    if closing is None:
        raise ValueError(f"{path}: frontmatter has no closing delimiter")
    raw = "\n".join(lines[1:closing])
    try:
        value = yaml.load(raw, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: invalid frontmatter YAML: {exc}") from exc
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{path}: frontmatter must be a mapping")
    return value


def _has_frontmatter_marker(path: Path) -> bool:
    """Match Jekyll's requirement that front matter starts on the first line."""
    try:
        with path.open("rb") as handle:
            return handle.readline(256).rstrip(b"\r\n") == b"---"
    except OSError as exc:
        raise ValueError(f"{path}: cannot inspect source page: {exc}") from exc


def validate_source(docs_dir: Path) -> list[str]:
    errors: list[str] = []
    pages: list[SourcePage] = []
    for path in sorted(candidate for candidate in docs_dir.rglob("*") if candidate.is_file()):
        relative = path.relative_to(docs_dir)
        if relative.parts and relative.parts[0] in IGNORED_SOURCE_ROOTS:
            continue
        try:
            if not _has_frontmatter_marker(path):
                continue
            frontmatter = _frontmatter(path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if frontmatter is None:
            continue
        permalink_value = frontmatter.get("permalink")
        peer_value = frontmatter.get("lang_peer")
        if permalink_value is not None and not isinstance(permalink_value, str):
            errors.append(f"{path}: permalink must be a string")
            permalink_value = None
        if peer_value is not None and not isinstance(peer_value, str):
            errors.append(f"{path}: lang_peer must be a string")
            peer_value = None
        try:
            permalink = (
                _canonical_site_path(permalink_value, field="permalink", source=path)
                if permalink_value is not None
                else None
            )
            peer = (
                _canonical_site_path(peer_value, field="lang_peer", source=path)
                if peer_value is not None
                else None
            )
        except ValueError as exc:
            errors.append(str(exc))
            continue
        implicit_output = (
            relative.with_suffix(".html").as_posix()
            if relative.suffix.lower() in MARKDOWN_SUFFIXES
            else relative.as_posix()
        )
        output_path = _output_path_for_url(permalink) if permalink else implicit_output
        pages.append(
            SourcePage(
                path=path,
                permalink=permalink,
                lang_peer=peer,
                output_path=output_path,
            )
        )

    by_permalink: dict[str, SourcePage] = {}
    by_output_path: dict[str, SourcePage] = {}
    for page in pages:
        previous_output = by_output_path.get(page.output_path)
        if previous_output is not None:
            errors.append(
                f"conflicting Jekyll output {page.output_path!r}: "
                f"{previous_output.path} and {page.path}"
            )
        else:
            by_output_path[page.output_path] = page

        if page.permalink is None:
            if page.lang_peer is not None:
                errors.append(f"{page.path}: lang_peer requires an explicit permalink")
            continue
        previous = by_permalink.get(page.permalink)
        if previous is not None:
            errors.append(
                f"duplicate permalink {page.permalink!r}: {previous.path} and {page.path}"
            )
        else:
            by_permalink[page.permalink] = page

    for page in pages:
        if page.lang_peer is None:
            continue
        target = by_permalink.get(page.lang_peer)
        if target is None:
            errors.append(f"{page.path}: lang_peer target does not exist: {page.lang_peer}")
        elif target.lang_peer != page.permalink:
            errors.append(
                f"{page.path}: lang_peer {page.lang_peer} is not reciprocal "
                f"(target points to {target.lang_peer!r})"
            )
        source_language = _site_language(page.permalink)
        target_language = _site_language(page.lang_peer)
        if {source_language, target_language} != {"en", "ja"}:
            errors.append(f"{page.path}: lang_peer must connect one /en/ page and one /ja/ page")
    return sorted(errors)


def _output_path_for_url(url: str) -> str:
    relative = url.lstrip("/")
    if not relative or url.endswith("/"):
        return f"{relative}index.html"
    return relative


def _site_language(url: str | None) -> str | None:
    if url is None:
        return None
    parts = PurePosixPath(url).parts
    return parts[1] if len(parts) > 1 and parts[1] in {"en", "ja"} else None


def _url_for_output(path: Path, site_dir: Path) -> str:
    relative = path.relative_to(site_dir).as_posix()
    if relative == "index.html":
        return "/"
    if relative.endswith("/index.html"):
        return f"/{relative[: -len('index.html')]}"
    return f"/{relative}"


def _html_parser(path: Path) -> LinkHTMLParser:
    parser = LinkHTMLParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser


def _iter_site_references(site_dir: Path) -> Iterator[Reference]:
    for path in sorted(site_dir.rglob("*.html")):
        source_url = _url_for_output(path, site_dir)
        parser = _html_parser(path)
        for raw_url, attribute in parser.references:
            yield Reference(path, source_url, raw_url.strip(), attribute)
    for path in sorted(site_dir.rglob("*.css")):
        source_url = _url_for_output(path, site_dir)
        text = path.read_text(encoding="utf-8")
        for match in CSS_URL_RE.finditer(text):
            yield Reference(path, source_url, match.group(2).strip(), "css[url]")


def _same_origin(split: Any, config: SiteConfig) -> bool:
    origin = urlsplit(config.origin)
    return split.scheme.lower() == origin.scheme and split.netloc.lower() == origin.netloc


def classify_reference(raw_url: str, source_url: str, config: SiteConfig) -> tuple[str, str]:
    """Return (internal|external|invalid|ignore, normalized URL/path)."""
    if not raw_url:
        return "ignore", raw_url
    split = urlsplit(raw_url)
    scheme = split.scheme.lower()
    if scheme in IGNORED_SCHEMES:
        return "ignore", raw_url
    if scheme and scheme not in {"http", "https"}:
        return "ignore", raw_url

    if scheme in {"http", "https"} or split.netloc:
        absolute = urlsplit(raw_url if scheme else f"{urlsplit(config.origin).scheme}:{raw_url}")
        normalized_absolute = urlunsplit(
            (absolute.scheme, absolute.netloc, absolute.path, absolute.query, "")
        )
        if _same_origin(absolute, config):
            path = absolute.path or "/"
            base = config.baseurl
            if base and path != base and not path.startswith(f"{base}/"):
                # A user/org Pages host can serve multiple project sites. An
                # absolute URL outside this project's baseurl is therefore an
                # external link and belongs to the scheduled network check.
                return "external", normalized_absolute
            internal_path = path[len(base) :] if base else path
            internal_path = internal_path or "/"
            return "internal", urlunsplit(
                ("", "", internal_path, absolute.query, absolute.fragment)
            )
        return "external", normalized_absolute

    if config.baseurl and split.path.startswith("/"):
        if split.path != config.baseurl and not split.path.startswith(f"{config.baseurl}/"):
            return "invalid", "root-relative URL is outside configured baseurl"
    joined = urljoin(source_url, raw_url)
    joined_split = urlsplit(joined)
    path = joined_split.path or source_url
    if config.baseurl and (path == config.baseurl or path.startswith(f"{config.baseurl}/")):
        path = path[len(config.baseurl) :] or "/"
    return "internal", urlunsplit(("", "", path, joined_split.query, joined_split.fragment))


def _target_candidates(site_dir: Path, path: str) -> list[Path]:
    relative = path.lstrip("/")
    target = site_dir / relative
    candidates: list[Path] = []
    if path.endswith("/") or not relative:
        candidates.append(target / "index.html")
    else:
        candidates.append(target)
        suffix = PurePosixPath(relative).suffix
        if not suffix:
            candidates.extend([target.with_suffix(".html"), target / "index.html"])
    return candidates


def _resolve_internal_target(site_dir: Path, normalized: str) -> tuple[Path | None, str | None]:
    split = urlsplit(normalized)
    decoded_path = unquote(split.path or "/")
    parts = PurePosixPath(decoded_path).parts
    if "\x00" in decoded_path or any(part == ".." for part in parts):
        return None, "path traversal is not allowed"
    root = site_dir.resolve()
    for candidate in _target_candidates(site_dir, decoded_path):
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            return None, "target escapes the built site"
        if resolved.is_file():
            return resolved, None
    return None, "target does not exist"


def _validate_built_site(site_dir: Path) -> None:
    if not site_dir.is_dir():
        raise ValueError(f"built site directory does not exist or is not a directory: {site_dir}")
    if not any(path.is_file() for path in site_dir.rglob("*.html")):
        raise ValueError(f"built site contains no HTML files: {site_dir}")


def validate_internal(site_dir: Path, config: SiteConfig) -> list[str]:
    _validate_built_site(site_dir)
    errors: list[str] = []
    anchor_cache: dict[Path, set[str]] = {}
    for reference in _iter_site_references(site_dir):
        kind, normalized = classify_reference(reference.raw_url, reference.source_url, config)
        context = f"{reference.source_path}: {reference.attribute}={reference.raw_url!r}"
        if kind == "invalid":
            errors.append(f"{context}: {normalized}")
            continue
        if kind != "internal":
            continue
        target, reason = _resolve_internal_target(site_dir, normalized)
        if target is None:
            errors.append(f"{context}: {reason}")
            continue
        fragment = unquote(urlsplit(normalized).fragment)
        if fragment and target.suffix.lower() == ".html":
            anchors = anchor_cache.get(target)
            if anchors is None:
                anchors = _html_parser(target).anchors
                anchor_cache[target] = anchors
            if fragment not in anchors:
                errors.append(f"{context}: anchor #{fragment} does not exist in {target}")
    return sorted(errors)


def collect_external_urls(site_dir: Path, config: SiteConfig) -> list[str]:
    urls: set[str] = set()
    for reference in _iter_site_references(site_dir):
        kind, normalized = classify_reference(reference.raw_url, reference.source_url, config)
        if kind == "external":
            urls.add(normalized)
    return sorted(urls)


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def load_allowlist(path: Path, *, today: date) -> tuple[set[str], list[str]]:
    errors: list[str] = []
    try:
        raw = _load_yaml_mapping(path)
    except ValueError as exc:
        return set(), [str(exc)]
    if raw.get("schema_version") != 1:
        errors.append(f"{path}: schema_version must be 1")
    entries = raw.get("entries")
    if not isinstance(entries, list):
        return set(), errors + [f"{path}: entries must be a list"]
    allowed: set[str] = set()
    for index, entry in enumerate(entries):
        prefix = f"{path}: entries[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix} must be a mapping")
            continue
        required = {"url", "reason", "owner", "issue", "expires_on"}
        missing = sorted(required - set(entry))
        if missing:
            errors.append(f"{prefix} missing fields: {', '.join(missing)}")
            continue
        if any(not isinstance(entry[key], str) or not entry[key].strip() for key in required):
            errors.append(f"{prefix} fields must be non-empty strings")
            continue
        url = urldefrag(entry["url"].strip())[0]
        split = urlsplit(url)
        if split.scheme not in {"http", "https"} or not split.netloc:
            errors.append(f"{prefix}.url must be an absolute HTTP(S) URL")
            continue
        if not re.fullmatch(r"https://github\.com/[^/]+/[^/]+/issues/\d+", entry["issue"]):
            errors.append(f"{prefix}.issue must be a GitHub Issue URL")
            continue
        try:
            expires_on = date.fromisoformat(entry["expires_on"])
        except ValueError:
            errors.append(f"{prefix}.expires_on must use YYYY-MM-DD")
            continue
        if expires_on < today:
            errors.append(f"{prefix} expired on {expires_on.isoformat()}")
            continue
        if url in allowed:
            errors.append(f"{prefix}.url duplicates another entry: {url}")
            continue
        allowed.add(url)
    return allowed, errors


def validate_allowlist(path: Path, *, today: date | None = None) -> list[str]:
    _allowed, errors = load_allowlist(path, today=today or datetime.now(timezone.utc).date())
    return errors


def load_success_cache(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: invalid external-link cache: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError(f"{path}: external-link cache schema_version must be 1")
    entries = raw.get("entries")
    if not isinstance(entries, dict):
        raise ValueError(f"{path}: external-link cache entries must be a mapping")
    return entries


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def validate_public_url(
    url: str,
    *,
    resolver: Callable[..., Any] = socket.getaddrinfo,
) -> tuple[str, ...]:
    split = urlsplit(url)
    if split.scheme not in {"http", "https"} or not split.hostname:
        raise ValueError("URL must use HTTP(S) and include a hostname")
    if split.username is not None or split.password is not None:
        raise ValueError("URL credentials are not allowed")
    try:
        port = split.port or (443 if split.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError(f"invalid port: {exc}") from exc
    try:
        answers = resolver(split.hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError(f"DNS resolution failed: {exc}") from exc
    addresses = {answer[4][0].split("%", 1)[0] for answer in answers if answer[4]}
    if not addresses:
        raise ValueError("DNS resolution returned no addresses")
    for address in sorted(addresses):
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as exc:
            raise ValueError(f"DNS returned an invalid address: {address}") from exc
        if (
            not parsed.is_global
            or parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_unspecified
            or parsed.is_multicast
            or parsed.is_reserved
        ):
            raise ValueError(f"DNS resolved to a non-public address: {address}")
    return tuple(sorted(addresses))


class LinkCheckFailure(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTP connection whose socket target is a previously validated IP."""

    def __init__(self, host: str, pinned_ip: str, port: int, *, timeout: float) -> None:
        super().__init__(host, port=port, timeout=timeout)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._pinned_ip, self.port), self.timeout, self.source_address
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to an IP while preserving hostname SNI/cert checks."""

    def __init__(self, host: str, pinned_ip: str, port: int, *, timeout: float) -> None:
        super().__init__(host, port=port, timeout=timeout, context=ssl.create_default_context())
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self._pinned_ip, self.port), self.timeout, self.source_address
        )
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


def _request_pinned(
    method: str,
    url: str,
    pinned_ip: str,
    *,
    timeout: float,
    max_bytes: int,
) -> LinkResponse:
    split = urlsplit(url)
    if not split.hostname:
        raise OSError("URL has no hostname")
    host = split.hostname.encode("idna").decode("ascii")
    port = split.port or (443 if split.scheme == "https" else 80)
    connection_type = _PinnedHTTPSConnection if split.scheme == "https" else _PinnedHTTPConnection
    connection = connection_type(host, pinned_ip, port, timeout=timeout)
    headers = {"User-Agent": "claude-trading-skills-docs-link-check/1.0"}
    if method == "GET":
        headers["Range"] = f"bytes=0-{max_bytes - 1}"
    target = urlunsplit(("", "", split.path or "/", split.query, ""))
    try:
        connection.request(method, target, headers=headers)
        response = connection.getresponse()
        if method == "GET":
            response.read(max_bytes)
        return LinkResponse(
            status=response.status,
            headers={name.lower(): value for name, value in response.headers.items()},
        )
    finally:
        connection.close()


def _check_url_once(
    url: str,
    *,
    requester: Callable[..., LinkResponse],
    resolver: Callable[..., Any],
    timeout: float,
    max_redirects: int,
    max_bytes: int,
) -> tuple[int, str]:
    current = url
    for redirect_count in range(max_redirects + 1):
        try:
            addresses = validate_public_url(current, resolver=resolver)
        except ValueError as exc:
            raise LinkCheckFailure(f"unsafe URL {current!r}: {exc}") from exc
        try:
            response = requester(
                "HEAD",
                current,
                addresses[0],
                timeout=timeout,
                max_bytes=max_bytes,
            )
            if response.status in HEAD_FALLBACK_STATUSES:
                response = requester(
                    "GET",
                    current,
                    addresses[0],
                    timeout=timeout,
                    max_bytes=max_bytes,
                )
            status = response.status
            if status in REDIRECT_STATUSES:
                location = response.headers.get("location") or response.headers.get("Location")
                if not location:
                    raise LinkCheckFailure(f"HTTP {status} redirect has no Location header")
                if redirect_count >= max_redirects:
                    raise LinkCheckFailure(f"redirect limit ({max_redirects}) exceeded")
                current = urljoin(current, location)
                continue
            if 200 <= status < 400:
                return status, current
            raise LinkCheckFailure(f"HTTP {status}", retryable=status in TRANSIENT_STATUSES)
        except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
            raise LinkCheckFailure(str(exc), retryable=True) from exc
    raise LinkCheckFailure(f"redirect limit ({max_redirects}) exceeded")


def check_url(
    url: str,
    *,
    requester: Callable[..., LinkResponse] = _request_pinned,
    resolver: Callable[..., Any] = socket.getaddrinfo,
    timeout: float,
    retries: int,
    max_redirects: int,
    max_bytes: int,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    attempts = 0
    while True:
        attempts += 1
        try:
            status, final_url = _check_url_once(
                url,
                requester=requester,
                resolver=resolver,
                timeout=timeout,
                max_redirects=max_redirects,
                max_bytes=max_bytes,
            )
            return {
                "attempts": attempts,
                "final_url": final_url,
                "outcome": "passed",
                "status": status,
            }
        except LinkCheckFailure as exc:
            if not exc.retryable or attempts > retries:
                return {
                    "attempts": attempts,
                    "error": str(exc),
                    "outcome": "failed",
                }
            sleep(min(2 ** (attempts - 1), 8))


def validate_external(
    site_dir: Path,
    config: SiteConfig,
    *,
    allowlist_path: Path,
    cache_path: Path,
    report_path: Path,
    cache_ttl_hours: int,
    retries: int,
    timeout: float,
    max_redirects: int,
    max_bytes: int,
    now: datetime | None = None,
    requester: Callable[..., LinkResponse] = _request_pinned,
    resolver: Callable[..., Any] = socket.getaddrinfo,
    sleep: Callable[[float], None] = time.sleep,
) -> list[str]:
    _validate_built_site(site_dir)
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    errors: list[str] = []
    allowed, allowlist_errors = load_allowlist(allowlist_path, today=now.date())
    errors.extend(allowlist_errors)
    try:
        cache = load_success_cache(cache_path)
    except ValueError as exc:
        cache = {}
        errors.append(str(exc))
    urls = collect_external_urls(site_dir, config)
    results: dict[str, dict[str, Any]] = {}
    updated_cache = dict(cache)
    for url in urls:
        if url in allowed:
            results[url] = {"outcome": "allowlisted"}
            continue
        cached = cache.get(url)
        if isinstance(cached, dict) and cached.get("outcome") == "passed":
            try:
                checked_at = _parse_utc(cached["checked_at"])
            except (KeyError, TypeError, ValueError):
                checked_at = datetime.min.replace(tzinfo=timezone.utc)
            age_hours = (now - checked_at).total_seconds() / 3600
            if 0 <= age_hours <= cache_ttl_hours:
                results[url] = {
                    "cache_age_hours": round(age_hours, 3),
                    "final_url": cached.get("final_url", url),
                    "outcome": "cached",
                    "status": cached.get("status"),
                }
                continue
        result = check_url(
            url,
            requester=requester,
            resolver=resolver,
            timeout=timeout,
            retries=retries,
            max_redirects=max_redirects,
            max_bytes=max_bytes,
            sleep=sleep,
        )
        results[url] = result
        if result["outcome"] == "passed":
            updated_cache[url] = {
                "checked_at": now.isoformat().replace("+00:00", "Z"),
                "final_url": result["final_url"],
                "outcome": "passed",
                "status": result["status"],
            }
        else:
            errors.append(f"{url}: {result.get('error', 'external check failed')}")
            updated_cache.pop(url, None)

    report = {
        "checked_at": now.isoformat().replace("+00:00", "Z"),
        "errors": sorted(errors),
        "results": results,
        "schema_version": 1,
        "summary": {
            "allowlisted": sum(r["outcome"] == "allowlisted" for r in results.values()),
            "cached": sum(r["outcome"] == "cached" for r in results.values()),
            "failed": sum(r["outcome"] == "failed" for r in results.values()),
            "passed": sum(r["outcome"] == "passed" for r in results.values()),
            "total": len(results),
        },
    }
    _write_json(report_path, report)
    _write_json(cache_path, {"entries": updated_cache, "schema_version": 1})
    return sorted(errors)


def _print_result(label: str, errors: Iterable[str]) -> int:
    materialized = list(errors)
    if materialized:
        print(f"ERROR: {label} failed with {len(materialized)} issue(s):")
        for error in materialized:
            print(f"  - {error}")
        return 1
    print(f"OK: {label}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    source = subparsers.add_parser("source", help="validate source frontmatter relationships")
    source.add_argument("--docs-dir", type=Path, default=PROJECT_ROOT / "docs")

    allowlist = subparsers.add_parser("allowlist", help="validate external-link allowlist")
    allowlist.add_argument(
        "--allowlist",
        type=Path,
        default=PROJECT_ROOT / "config" / "docs-external-link-allowlist.json",
    )

    internal = subparsers.add_parser("internal", help="validate built internal links/assets")
    internal.add_argument("--site-dir", type=Path, required=True)
    internal.add_argument("--config", type=Path, default=PROJECT_ROOT / "docs" / "_config.yml")

    external = subparsers.add_parser("external", help="validate built external links")
    external.add_argument("--site-dir", type=Path, required=True)
    external.add_argument("--config", type=Path, default=PROJECT_ROOT / "docs" / "_config.yml")
    external.add_argument(
        "--allowlist",
        type=Path,
        default=PROJECT_ROOT / "config" / "docs-external-link-allowlist.json",
    )
    external.add_argument("--cache", type=Path, required=True)
    external.add_argument("--report", type=Path, required=True)
    external.add_argument("--cache-ttl-hours", type=int, default=168)
    external.add_argument("--retries", type=int, default=2)
    external.add_argument("--timeout", type=float, default=15.0)
    external.add_argument("--max-redirects", type=int, default=5)
    external.add_argument("--max-bytes", type=int, default=4096)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "source":
            return _print_result("docs source validation", validate_source(args.docs_dir))
        if args.command == "allowlist":
            return _print_result(
                "docs external-link allowlist validation",
                validate_allowlist(args.allowlist),
            )
        config = load_site_config(args.config)
        if args.command == "internal":
            return _print_result(
                "built docs internal-link validation",
                validate_internal(args.site_dir, config),
            )
        return _print_result(
            "built docs external-link validation",
            validate_external(
                args.site_dir,
                config,
                allowlist_path=args.allowlist,
                cache_path=args.cache,
                report_path=args.report,
                cache_ttl_hours=args.cache_ttl_hours,
                retries=args.retries,
                timeout=args.timeout,
                max_redirects=args.max_redirects,
                max_bytes=args.max_bytes,
            ),
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
