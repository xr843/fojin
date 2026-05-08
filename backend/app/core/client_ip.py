"""Client IP extraction helper.

Behind our Nginx reverse proxy the X-Forwarded-For header is built using
``$proxy_add_x_forwarded_for`` which APPENDS the real connection IP to any
client-supplied value. So for a request like::

    X-Forwarded-For: 1.2.3.4, 5.6.7.8

``5.6.7.8`` is the IP nginx actually saw on the wire (trusted), while
``1.2.3.4`` is whatever the client put in the header (untrusted, may be
spoofed). We must therefore take the LAST entry, not the first.

Taking ``split(",")[0]`` lets any external client forge their source IP and
bypass IP-based rate limiting / poison password-change audit logs. This
helper centralises the correct extraction so every call site behaves the
same.
"""

from __future__ import annotations

from fastapi import Request


def get_real_client_ip(request: Request, default: str | None = "unknown") -> str | None:
    """Return the real client IP behind a trusted reverse proxy.

    Strategy:
      1. If ``X-Forwarded-For`` is present, take the LAST entry (the IP that
         nginx itself appended via ``$proxy_add_x_forwarded_for``).
      2. Otherwise fall back to ``request.client.host`` (direct connection,
         e.g. when nginx is bypassed in dev).
      3. Otherwise return ``default``.

    Args:
        request: Starlette/FastAPI Request.
        default: Value to return when no IP can be determined. Pass ``None``
            for call sites that want to store NULL on missing IP.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # X-Forwarded-For: client, proxy1, proxy2, <nginx-appended-real-ip>
        # The last entry is the IP nginx observed on the wire — trust that.
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]
    if request.client and request.client.host:
        return request.client.host
    return default
