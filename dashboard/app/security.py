"""Shared request checks for the pages that save data."""

from __future__ import annotations

from urllib.parse import urlsplit

from flask import request


def same_origin() -> bool:
    """Block forms posted from other sites (CSRF, cross-site request forgery).

    Browsers send an Origin header on every form POST. It has to match the host
    this page was served from. Caddy passes the Host header through unchanged.
    """
    source = request.headers.get("Origin") or request.headers.get("Referer")
    if not source:
        return False
    return urlsplit(source).netloc == request.host
