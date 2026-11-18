"""Hardened loopback, Fetch-Metadata & per-boot CSRF security guards for Studio (TRAP-08).

Every Studio request passes:
1. Loopback client IP check (``127.0.0.1`` / ``::1`` / ``testclient`` in pytest)
2. Loopback ``Origin`` check (when present) and ``Sec-Fetch-Site != cross-site``
3. Every write route additionally requires exact per-boot 32-byte random hex
   ``X-Studio-Token`` header (constant-time ``hmac.compare_digest``).
"""

from __future__ import annotations

import hmac
import ipaddress
import re
import secrets
from urllib.parse import urlparse

from fastapi import HTTPException, Request

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")


def generate_studio_token() -> str:
    """Return a fresh 32-byte cryptographically random hex token per server boot."""
    return secrets.token_hex(32)


def is_valid_project_id(project_id: str | None) -> bool:
    """Return True if ``project_id`` is a safe single-segment slug (no traversal/injection)."""
    return isinstance(project_id, str) and bool(PROJECT_ID_RE.fullmatch(project_id))


def validate_project_id(project_id: str | None) -> str:
    if not is_valid_project_id(project_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid project_id: must match ^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$.",
        )
    return str(project_id)


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
    """Return True if ``Origin`` header is absent or strictly http(s)://127.0.0.1|localhost|::1."""
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
    """Enforce loopback client IP, loopback Origin, and Fetch-Metadata guard."""
    client_host = request.client.host if request.client else None
    if not is_loopback_client(client_host):
        raise HTTPException(status_code=403, detail="Studio is restricted to loopback clients.")
    origin = request.headers.get("origin")
    if origin and not is_loopback_origin(origin):
        raise HTTPException(status_code=403, detail="Cross-origin requests to Studio are forbidden.")
    sec_fetch_site = (request.headers.get("sec-fetch-site") or "").strip().lower()
    if sec_fetch_site == "cross-site":
        raise HTTPException(status_code=403, detail="Cross-site requests to Studio are forbidden.")


def require_studio_write(request: Request, expected_token: str) -> None:
    """Enforce loopback IP, loopback Origin, Fetch-Metadata, and per-boot ``X-Studio-Token``."""
    require_loopback(request)
    provided = request.headers.get("x-studio-token") or ""
    if not expected_token or not provided or not hmac.compare_digest(provided, expected_token):
        raise HTTPException(status_code=403, detail="Missing or invalid X-Studio-Token.")
