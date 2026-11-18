"""Hardened loopback & per-boot CSRF security guards for Studio (TRAP-08).

Every state-changing route (POST/DELETE/PUT/PATCH) must pass:
1. Loopback client IP check (``127.0.0.1`` / ``::1`` / ``testclient`` in pytest)
2. Loopback ``Origin`` check (when ``Origin`` header is present)
3. Per-boot 32-byte random hex CSRF token via ``X-Studio-Token`` (constant-time compare)
"""

from __future__ import annotations

import hmac
import ipaddress
import secrets
from urllib.parse import urlparse

from fastapi import HTTPException, Request

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def generate_studio_token() -> str:
    """Return a fresh 32-byte cryptographically random hex token per server boot."""
    return secrets.token_hex(32)


def is_loopback_client(host: str | None) -> bool:
    """Return True if the connecting peer address is loopback."""
    if not host:
        return False
    cleaned = host.strip().lower()
    if cleaned in ("localhost", "testclient"):
        return True
    try:
        ip = ipaddress.ip_address(cleaned.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return bool(ip.is_loopback)


def is_loopback_origin(origin: str | None) -> bool:
    """Return True if ``Origin`` header is absent or strictly http(s)://127.0.0.1|localhost."""
    if not origin or not origin.strip():
        return True
    try:
        parsed = urlparse(origin.strip())
    except ValueError:
        return False
    if (parsed.scheme or "").lower() not in ("http", "https"):
        return False
    host = (parsed.hostname or "").strip().lower()
    return host in LOOPBACK_HOSTS


def require_loopback(request: Request) -> None:
    """Enforce loopback client IP and loopback Origin on every Studio API call."""
    client_host = request.client.host if request.client else None
    if not is_loopback_client(client_host):
        raise HTTPException(status_code=403, detail="Studio is restricted to loopback clients.")
    origin = request.headers.get("origin")
    if origin and not is_loopback_origin(origin):
        raise HTTPException(status_code=403, detail="Cross-origin requests to Studio are forbidden.")


def require_studio_write(request: Request, expected_token: str) -> None:
    """Enforce loopback IP, loopback Origin, and exact per-boot ``X-Studio-Token`` CSRF header."""
    require_loopback(request)
    provided = request.headers.get("x-studio-token") or ""
    if not expected_token or not provided or not hmac.compare_digest(provided, expected_token):
        raise HTTPException(status_code=403, detail="Missing or invalid X-Studio-Token.")
