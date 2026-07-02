"""BYOK custom provider URL safety tests."""

import socket
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ServiceError


def _fake_user(uid=42):
    u = MagicMock()
    u.id = uid
    u.username = "u"
    u.email = "u@example.com"
    u.display_name = "u"
    u.role = "user"
    u.is_active = True
    u.created_at = datetime.now(UTC)
    u.encrypted_api_key = None
    u.api_key_kdf_version = 2
    u.api_provider = None
    u.api_model = None
    u.api_custom_url = None
    return u


@pytest.mark.anyio
@pytest.mark.parametrize(
    "custom_url",
    [
        "http://llm.example.com/v1",
        "ftp://llm.example.com/v1",
        "https://localhost:8000/v1",
        "https://127.0.0.1:8000/v1",
        "https://127.1/v1",
        "https://0177.0.0.1/v1",
        "https://0x7f.0.0.1/v1",
        "https://[::1]/v1",
        "https://10.0.0.5/v1",
        "https://172.16.0.5/v1",
        "https://192.168.1.5/v1",
        "https://169.254.169.254/latest/meta-data",
        "https://llm.example.com:bad/v1",
        "https://user:pass@llm.example.com/v1",
    ],
)
async def test_save_custom_api_key_rejects_unsafe_custom_url(client, custom_url):
    fake_user = _fake_user()
    mock_db = AsyncMock()

    from app.core.deps import get_current_user
    from app.database import get_db as real_get_db
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[real_get_db] = lambda: mock_db
    try:
        resp = await client.put(
            "/api/auth/api-key",
            json={
                "api_key": "sk-1234567890abcdef",
                "provider": "custom",
                "model": "custom-model",
                "custom_url": custom_url,
            },
        )
        assert resp.status_code == 422
        mock_db.commit.assert_not_awaited()
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(real_get_db, None)


@pytest.mark.anyio
async def test_save_custom_api_key_accepts_public_https_custom_url(client):
    fake_user = _fake_user()
    mock_db = AsyncMock()

    from app.core.deps import get_current_user
    from app.database import get_db as real_get_db
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[real_get_db] = lambda: mock_db
    try:
        resp = await client.put(
            "/api/auth/api-key",
            json={
                "api_key": "sk-1234567890abcdef",
                "provider": "custom",
                "model": "custom-model",
                "custom_url": "https://llm.example.com/v1/",
            },
        )
        assert resp.status_code == 200, resp.text
        assert fake_user.api_custom_url == "https://llm.example.com/v1"
        assert resp.json()["custom_url"] == "https://llm.example.com/v1"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(real_get_db, None)


def test_resolve_llm_config_rejects_unsafe_persisted_custom_url(monkeypatch):
    from app.services import chat

    user = _fake_user()
    user.id = 7
    user.encrypted_api_key = "ciphertext"
    user.api_provider = "custom"
    user.api_model = "custom-model"
    user.api_custom_url = "https://127.0.0.1:8000/v1"

    monkeypatch.setattr(chat, "decrypt_api_key", lambda *_args, **_kwargs: "sk-user")

    with pytest.raises(ServiceError, match="自定义 API 地址"):
        chat._resolve_llm_config(user)


@pytest.mark.anyio
async def test_runtime_dns_guard_rejects_hostname_resolving_to_private_ip(monkeypatch):
    from app.core.url_security import ensure_public_https_url_resolves

    def fake_getaddrinfo(host, port, *args, **kwargs):
        assert host == "llm.example.com"
        assert port == 443
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(ValueError, match="解析到"):
        await ensure_public_https_url_resolves("https://llm.example.com/v1", label="自定义 API 地址")


@pytest.mark.anyio
async def test_public_https_resolution_returns_pinned_ip(monkeypatch):
    from app.core.url_security import resolve_public_https_url

    def fake_getaddrinfo(host, port, *args, **kwargs):
        assert host == "llm.example.com"
        assert port == 443
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    resolution = await resolve_public_https_url(
        "https://llm.example.com/v1/", label="自定义 API 地址"
    )

    assert resolution.url == "https://llm.example.com/v1"
    assert resolution.host == "llm.example.com"
    assert resolution.port == 443
    assert resolution.pinned_ip == "93.184.216.34"


@pytest.mark.anyio
async def test_pinned_network_backend_connects_validated_host_to_pinned_ip():
    import httpcore

    from app.core.url_security import PinnedHTTPSNetworkBackend, PublicHttpsResolution

    class RecordingBackend(httpcore.AsyncNetworkBackend):
        def __init__(self):
            self.calls = []

        async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
            self.calls.append((host, port))
            return MagicMock()

        async def connect_unix_socket(self, path, timeout=None, socket_options=None):
            raise AssertionError("unix sockets should not be used")

        async def sleep(self, seconds):
            return None

    delegate = RecordingBackend()
    backend = PinnedHTTPSNetworkBackend(
        PublicHttpsResolution(
            url="https://llm.example.com/v1",
            host="llm.example.com",
            port=443,
            resolved_ips=("93.184.216.34",),
        ),
        delegate=delegate,
    )

    await backend.connect_tcp("llm.example.com", 443)
    await backend.connect_tcp("other.example.com", 443)

    assert delegate.calls == [
        ("93.184.216.34", 443),
        ("other.example.com", 443),
    ]


@pytest.mark.anyio
async def test_custom_byok_http_client_uses_pinned_transport(monkeypatch):
    from app.services import chat

    transport = object()
    pin = AsyncMock(return_value=transport)
    client_cls = MagicMock(return_value="client")
    monkeypatch.setattr(chat, "create_pinned_https_transport", pin)
    monkeypatch.setattr(chat.httpx, "AsyncClient", client_cls)

    client = await chat._build_llm_http_client(
        "https://llm.example.com/v1", "custom", 60
    )

    assert client == "client"
    pin.assert_awaited_once_with("https://llm.example.com/v1", label="自定义 API 地址")
    client_cls.assert_called_once_with(timeout=60, transport=transport)


@pytest.mark.anyio
async def test_prepare_chat_rejects_custom_byok_when_runtime_dns_guard_fails(monkeypatch):
    from app.services import chat

    user = _fake_user()
    user.id = 7
    user.encrypted_api_key = "ciphertext"
    user.api_provider = "custom"
    user.api_model = "custom-model"
    user.api_custom_url = "https://llm.example.com/v1"

    guard = AsyncMock(side_effect=ValueError("自定义 API 地址 解析到内网地址"))
    monkeypatch.setattr(chat, "decrypt_api_key", lambda *_args, **_kwargs: "sk-user")
    monkeypatch.setattr(chat, "ensure_public_https_url_resolves", guard)

    with pytest.raises(ServiceError, match="自定义 API 地址"):
        await chat._prepare_chat(AsyncMock(), None, "测试问题", user=user)

    guard.assert_awaited_once_with("https://llm.example.com/v1", label="自定义 API 地址")
