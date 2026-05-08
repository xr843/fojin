"""Tests for app.core.client_ip.get_real_client_ip.

Locks in the trust-boundary fix: when sitting behind nginx with
``proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for``, the
LAST entry of the header is the IP nginx itself observed on the wire.
A client supplying ``X-Forwarded-For: 1.2.3.4`` must NOT be able to
poison rate-limit keys or audit logs by having ``1.2.3.4`` extracted.
"""

from unittest.mock import MagicMock

from app.core.client_ip import get_real_client_ip


class _CaseInsensitiveHeaders:
    """Tiny stand-in for starlette.datastructures.Headers (case-insensitive get)."""

    def __init__(self, raw: dict | None):
        self._d = {k.lower(): v for k, v in (raw or {}).items()}

    def get(self, key, default=None):
        return self._d.get(key.lower(), default)


def _req(headers: dict | None = None, client_host: str | None = "127.0.0.1"):
    r = MagicMock()
    r.headers = _CaseInsensitiveHeaders(headers)
    if client_host is None:
        r.client = None
    else:
        r.client = MagicMock()
        r.client.host = client_host
    return r


def test_xff_takes_last_entry_not_first():
    # Attacker forges 1.2.3.4; nginx appends the real on-the-wire IP 5.6.7.8.
    req = _req({"X-Forwarded-For": "1.2.3.4, 5.6.7.8"})
    assert get_real_client_ip(req) == "5.6.7.8"


def test_xff_single_entry_returned_as_is():
    req = _req({"X-Forwarded-For": "9.9.9.9"})
    assert get_real_client_ip(req) == "9.9.9.9"


def test_xff_with_three_hops_picks_last():
    req = _req({"X-Forwarded-For": "1.1.1.1, 2.2.2.2, 3.3.3.3"})
    assert get_real_client_ip(req) == "3.3.3.3"


def test_xff_strips_whitespace():
    req = _req({"X-Forwarded-For": "1.2.3.4 ,   5.6.7.8   "})
    assert get_real_client_ip(req) == "5.6.7.8"


def test_xff_empty_falls_back_to_client_host():
    req = _req({}, client_host="10.0.0.1")
    assert get_real_client_ip(req) == "10.0.0.1"


def test_xff_blank_string_falls_back_to_client_host():
    # All-comma / whitespace-only header should not be trusted.
    req = _req({"X-Forwarded-For": " , , "}, client_host="10.0.0.1")
    assert get_real_client_ip(req) == "10.0.0.1"


def test_no_xff_no_client_returns_default():
    req = _req({}, client_host=None)
    assert get_real_client_ip(req) == "unknown"


def test_no_xff_no_client_custom_default_none():
    req = _req({}, client_host=None)
    assert get_real_client_ip(req, default=None) is None


def test_attacker_forging_does_not_leak_into_result():
    # Even if an attacker stuffs many forged hops, nginx-appended last hop wins.
    forged = ", ".join([f"10.{i}.0.1" for i in range(10)])
    req = _req({"X-Forwarded-For": f"{forged}, 203.0.113.7"})
    assert get_real_client_ip(req) == "203.0.113.7"
