"""URL validation helpers for server-side outbound requests."""

import asyncio
import re
import socket
from ipaddress import IPv4Address, IPv6Address, ip_address
from urllib.parse import urlsplit, urlunsplit

_NUMERIC_ADDRESS_LABEL_RE = re.compile(r"(?:0x[0-9a-f]+|[0-9]+)", re.IGNORECASE)

_BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
}
_BLOCKED_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".lan",
    ".home",
)


def _ip_is_blocked(parsed_ip: IPv4Address | IPv6Address) -> bool:
    return (
        parsed_ip.is_private
        or parsed_ip.is_loopback
        or parsed_ip.is_link_local
        or parsed_ip.is_multicast
        or parsed_ip.is_reserved
        or parsed_ip.is_unspecified
    )


def _host_is_blocked(host: str) -> bool:
    normalized = host.rstrip(".").lower()
    if normalized in _BLOCKED_HOSTS or any(normalized.endswith(suffix) for suffix in _BLOCKED_SUFFIXES):
        return True

    try:
        parsed_ip = ip_address(normalized)
    except ValueError:
        if "." not in normalized:
            return True
        labels = normalized.split(".")
        return all(_NUMERIC_ADDRESS_LABEL_RE.fullmatch(label) for label in labels)

    return _ip_is_blocked(parsed_ip)


def normalize_public_https_url(raw_url: str | None, *, label: str = "URL") -> str:
    """Return a normalized public HTTPS URL or raise ValueError.

    This is a static guard for user-configured outbound API base URLs. It blocks
    the obvious SSRF classes before the backend ever constructs an httpx request:
    non-HTTPS schemes, credentials in the authority, local hostnames, private IP
    literals, link-local metadata addresses, and single-label internal hosts.
    """
    raw = (raw_url or "").strip()
    if not raw:
        raise ValueError(f"{label} 不能为空")

    parts = urlsplit(raw)
    if parts.scheme.lower() != "https":
        raise ValueError(f"{label} 必须使用 https://")
    if not parts.hostname or not parts.netloc:
        raise ValueError(f"{label} 必须包含有效主机名")
    try:
        _ = parts.port
    except ValueError as exc:
        raise ValueError(f"{label} 包含无效端口") from exc
    if parts.username or parts.password:
        raise ValueError(f"{label} 不能包含用户名或密码")
    if parts.query or parts.fragment:
        raise ValueError(f"{label} 不能包含 query 或 fragment")
    if _host_is_blocked(parts.hostname):
        raise ValueError(f"{label} 不能指向 localhost、内网或保留地址")

    normalized_path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), normalized_path, "", ""))


async def ensure_public_https_url_resolves(raw_url: str | None, *, label: str = "URL") -> str:
    """Return the normalized URL after rejecting unsafe runtime DNS results."""
    normalized = normalize_public_https_url(raw_url, label=label)
    parts = urlsplit(normalized)
    host = parts.hostname
    if not host:
        raise ValueError(f"{label} 必须包含有效主机名")

    try:
        parsed_ip = ip_address(host)
    except ValueError:
        parsed_ip = None
    if parsed_ip is not None:
        if _ip_is_blocked(parsed_ip):
            raise ValueError(f"{label} 解析到 localhost、内网或保留地址")
        return normalized

    port = parts.port or 443
    try:
        addrinfos = await asyncio.get_running_loop().getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ValueError(f"{label} 主机名无法解析") from exc

    resolved_ips: set[IPv4Address | IPv6Address] = set()
    for *_, sockaddr in addrinfos:
        try:
            resolved_ips.add(ip_address(sockaddr[0]))
        except (IndexError, ValueError):
            raise ValueError(f"{label} 主机名解析结果无效") from None

    if not resolved_ips:
        raise ValueError(f"{label} 主机名无法解析")
    if any(_ip_is_blocked(ip) for ip in resolved_ips):
        raise ValueError(f"{label} 解析到 localhost、内网或保留地址")
    return normalized
