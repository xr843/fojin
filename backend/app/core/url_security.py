"""URL validation helpers for server-side outbound requests."""

import asyncio
import re
import socket
from collections.abc import Iterable
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_address
from urllib.parse import urlsplit, urlunsplit

import httpcore
import httpx
from httpcore._backends.auto import AutoBackend
from httpx._config import DEFAULT_LIMITS, Limits, create_ssl_context
from httpx._transports.default import SOCKET_OPTION
from httpx._types import CertTypes

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


@dataclass(frozen=True)
class PublicHttpsResolution:
    url: str
    host: str
    port: int
    resolved_ips: tuple[str, ...]

    @property
    def pinned_ip(self) -> str:
        return self.resolved_ips[0]


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
    return (await resolve_public_https_url(raw_url, label=label)).url


async def resolve_public_https_url(
    raw_url: str | None, *, label: str = "URL"
) -> PublicHttpsResolution:
    """Return normalized URL plus public IPs validated for request pinning."""
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
        return PublicHttpsResolution(
            url=normalized,
            host=host.rstrip(".").lower(),
            port=parts.port or 443,
            resolved_ips=(str(parsed_ip),),
        )

    port = parts.port or 443
    try:
        addrinfos = await asyncio.get_running_loop().getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ValueError(f"{label} 主机名无法解析") from exc

    resolved_ips: list[IPv4Address | IPv6Address] = []
    for *_, sockaddr in addrinfos:
        try:
            resolved_ip = ip_address(sockaddr[0])
        except (IndexError, ValueError):
            raise ValueError(f"{label} 主机名解析结果无效") from None
        if resolved_ip not in resolved_ips:
            resolved_ips.append(resolved_ip)

    if not resolved_ips:
        raise ValueError(f"{label} 主机名无法解析")
    if any(_ip_is_blocked(ip) for ip in resolved_ips):
        raise ValueError(f"{label} 解析到 localhost、内网或保留地址")
    return PublicHttpsResolution(
        url=normalized,
        host=host.rstrip(".").lower(),
        port=port,
        resolved_ips=tuple(str(ip) for ip in resolved_ips),
    )


class PinnedHTTPSNetworkBackend(httpcore.AsyncNetworkBackend):
    """httpcore network backend that connects one validated host to a pinned IP.

    The request URL still uses the original hostname, so Host and TLS SNI stay
    correct; only the TCP connect target is swapped to the public IP already
    returned by ``resolve_public_https_url``.
    """

    def __init__(
        self,
        resolution: PublicHttpsResolution,
        *,
        delegate: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self._host = resolution.host.rstrip(".").lower()
        self._port = resolution.port
        self._pinned_ip = resolution.pinned_ip
        self._delegate = delegate or AutoBackend()

    @staticmethod
    def _normalize_host(host: str | bytes) -> str:
        if isinstance(host, bytes):
            host = host.decode("idna")
        return host.rstrip(".").lower()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        connect_host = (
            self._pinned_ip
            if self._normalize_host(host) == self._host and port == self._port
            else host
        )
        return await self._delegate.connect_tcp(
            connect_host,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        return await self._delegate.connect_unix_socket(
            path,
            timeout=timeout,
            socket_options=socket_options,
        )

    async def sleep(self, seconds: float) -> None:
        await self._delegate.sleep(seconds)


class PinnedHTTPSAsyncTransport(httpx.AsyncHTTPTransport):
    """Async HTTP transport that pins TCP connects for one public HTTPS URL."""

    def __init__(
        self,
        resolution: PublicHttpsResolution,
        *,
        verify: bool | str = True,
        cert: CertTypes | None = None,
        trust_env: bool = True,
        http1: bool = True,
        http2: bool = False,
        limits: Limits = DEFAULT_LIMITS,
        retries: int = 0,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> None:
        ssl_context = create_ssl_context(
            verify=verify,
            cert=cert,
            trust_env=trust_env,
        )
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl_context,
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            http1=http1,
            http2=http2,
            retries=retries,
            network_backend=PinnedHTTPSNetworkBackend(resolution),
            socket_options=socket_options,
        )


async def create_pinned_https_transport(
    raw_url: str | None, *, label: str = "URL"
) -> PinnedHTTPSAsyncTransport:
    resolution = await resolve_public_https_url(raw_url, label=label)
    return PinnedHTTPSAsyncTransport(resolution)
