"""Connect-time SSRF protection for URL intake and media downloads.

Combines pre-flight URL/IP validation with a thread-local ``socket.getaddrinfo``
guard so HTTP 302 redirects, DNS rebinding, and nested yt-dlp stream/manifest
URLs are verified immediately before any socket connects.
"""

from __future__ import annotations

import contextlib
import ipaddress
import socket
import threading
from typing import Any, Iterator
from urllib.parse import urlparse

_CGNAT_NET = ipaddress.ip_network("100.64.0.0/10")
_ALLOWED_SCHEMES = frozenset({"http", "https"})

_install_lock = threading.Lock()
_active_guards = 0
_real_getaddrinfo = socket.getaddrinfo
_thread_state = threading.local()


class SSRFBlockedError(ValueError):
    """Raised when a URL or resolved network destination is non-public."""


def is_public_ip(ip_str: str) -> bool:
    """Return True only if ``ip_str`` is a globally routable public IP address."""
    if not isinstance(ip_str, str) or not ip_str.strip():
        return False
    # Strip IPv6 zone index (e.g. fe80::1%eth0) before parsing.
    cleaned = ip_str.strip().split("%", 1)[0]
    try:
        ip = ipaddress.ip_address(cleaned)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT_NET:
        return False
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return False
    return bool(ip.is_global)


def _check_addrinfo_results(host: Any, results: list[Any]) -> list[Any]:
    if not results:
        raise SSRFBlockedError(f"DNS returned no addresses for host {host!r}")
    for entry in results:
        sockaddr = entry[4]
        ip_str = sockaddr[0] if isinstance(sockaddr, (tuple, list)) and sockaddr else ""
        if not is_public_ip(str(ip_str)):
            raise SSRFBlockedError(
                f"Blocked non-public destination {ip_str!r} resolved for host {host!r}"
            )
    return results


def _guarded_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):  # noqa: A002
    results = _real_getaddrinfo(host, port, family, type, proto, flags)
    if getattr(_thread_state, "depth", 0) > 0:
        _check_addrinfo_results(host, results)
    return results


@contextlib.contextmanager
def guarded() -> Iterator[None]:
    """Block connections to non-public IPs on the current thread at resolve time.

    Nested calls on the same thread are reference-counted. Other threads without
    an active ``guarded()`` context are unaffected.
    """
    global _active_guards, _real_getaddrinfo
    with _install_lock:
        if _active_guards == 0:
            _real_getaddrinfo = socket.getaddrinfo
            socket.getaddrinfo = _guarded_getaddrinfo  # type: ignore[assignment]
        _active_guards += 1
    _thread_state.depth = getattr(_thread_state, "depth", 0) + 1
    try:
        yield
    finally:
        _thread_state.depth = max(0, getattr(_thread_state, "depth", 1) - 1)
        with _install_lock:
            _active_guards = max(0, _active_guards - 1)
            if _active_guards == 0 and socket.getaddrinfo is _guarded_getaddrinfo:
                socket.getaddrinfo = _real_getaddrinfo


def assert_public_host(host: str) -> None:
    """Resolve ``host`` and verify every returned IP address is publicly routable."""
    if not isinstance(host, str) or not host.strip():
        raise SSRFBlockedError("Hostname must be non-empty")
    hostname = host.strip().strip("[]")
    try:
        ipaddress.ip_address(hostname.split("%", 1)[0])
    except ValueError:
        pass
    else:
        if not is_public_ip(hostname):
            raise SSRFBlockedError(f"Blocked non-public IP literal {hostname!r}")
        return

    try:
        results = _real_getaddrinfo(hostname, None)
    except OSError as exc:
        raise SSRFBlockedError(f"Could not safely resolve host {hostname!r}: {exc}") from exc
    _check_addrinfo_results(hostname, results)


def assert_public_url(url: str, *, resolve_dns: bool = True) -> None:
    """Validate URL scheme and verify its target host is publicly routable."""
    if not isinstance(url, str) or not url.strip():
        raise SSRFBlockedError("URL must be a non-empty string")
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise SSRFBlockedError(f"Blocked unsupported URL scheme {scheme!r}")
    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlockedError(f"Missing hostname in URL {url!r}")
    if resolve_dns:
        assert_public_host(hostname)
    else:
        # Even without DNS, immediately reject localhost and literal private/loopback IPs.
        cleaned = hostname.strip().strip("[]").split("%", 1)[0].lower()
        if cleaned == "localhost" or cleaned.endswith(".localhost"):
            raise SSRFBlockedError(f"Blocked loopback hostname {hostname!r}")
        try:
            ipaddress.ip_address(cleaned)
        except ValueError:
            return
        if not is_public_ip(cleaned):
            raise SSRFBlockedError(f"Blocked non-public IP literal {hostname!r}")


def _iter_info_urls(info: Any) -> Iterator[str]:
    """Yield stream, manifest, and format URLs extracted by yt-dlp."""
    if not isinstance(info, dict):
        return
    for key in ("url", "manifest_url", "webpage_url"):
        val = info.get(key)
        if isinstance(val, str) and val.strip():
            yield val.strip()
    for list_key in ("requested_formats", "formats", "requested_downloads", "entries"):
        items = info.get(list_key)
        if isinstance(items, (list, tuple)):
            for item in items:
                if isinstance(item, dict):
                    yield from _iter_info_urls(item)


def assert_public_urls(info: dict[str, Any], *, resolve_dns: bool = True) -> None:
    """Validate every extracted stream/manifest URL inside a yt-dlp info dict."""
    seen: set[str] = set()
    for url in _iter_info_urls(info):
        if url in seen:
            continue
        seen.add(url)
        assert_public_url(url, resolve_dns=resolve_dns)
