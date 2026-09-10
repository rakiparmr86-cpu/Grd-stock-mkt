"""SSRF guard for ad-hoc crawl requests coming from the frontend.

Rejects non-HTTP(S) URLs and hosts that resolve to loopback / private /
link-local / reserved IP ranges — unless ``CRAWLER_ALLOW_PRIVATE=true`` (dev).
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlparse

from app.core.config import settings


class UnsafeUrlError(ValueError):
    pass


def _is_bad_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return (
        addr.is_loopback
        or addr.is_private
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def assert_public_url(
    url: str,
    *,
    resolver: Callable[[str], list[str]] | None = None,
) -> None:
    """Raise :class:`UnsafeUrlError` if ``url`` is not safe to fetch server-side."""
    if settings.crawler_allow_private:
        return

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"only http/https URLs allowed, got {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("URL has no host")
    if host.lower() in ("localhost", "localhost.localdomain") or host.endswith(".localhost"):
        raise UnsafeUrlError("refusing to crawl localhost")

    resolve = resolver or _default_resolver
    try:
        ips = resolve(host)
    except OSError as exc:
        raise UnsafeUrlError(f"cannot resolve host {host!r}: {exc}") from exc
    if not ips:
        raise UnsafeUrlError(f"host {host!r} resolved to nothing")
    bad = [ip for ip in ips if _is_bad_ip(ip)]
    if bad:
        raise UnsafeUrlError(f"host {host!r} resolves to a non-public address ({bad[0]})")


def _default_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None)
    return list({info[4][0] for info in infos})
