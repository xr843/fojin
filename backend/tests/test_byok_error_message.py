"""Unit tests for _byok_error_message — the BYOK upstream-error → friendly
Chinese mapping. It's a branch-dense pure function on the /chat path that was
previously uncovered: a wrong model id or insufficient balance commonly hides
behind a generic 401/400, and this function is what surfaces the real cause.
"""
import httpx
import pytest

from app.services.chat import _byok_error_message


def _status_error(body: str, status: int) -> httpx.HTTPStatusError:
    """Build an httpx.HTTPStatusError whose response.text is `body` (the
    function reads exc.response.text[:600] to sniff the provider's message)."""
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    response = httpx.Response(status, text=body, request=request)
    return httpx.HTTPStatusError("upstream error", request=request, response=response)


# (body, status, substring that MUST appear in the returned message)
_CASES = [
    # Model-not-found / not-authorized — recognised from the body regardless of status
    ("model not found", 404, "模型 ID 不存在"),
    ('{"error": {"code": "model_not_found"}}', 400, "模型 ID 不存在"),
    ("模型不存在", 400, "模型 ID 不存在"),
    ("该模型未开通", 403, "模型 ID 不存在"),
    # Insufficient balance / quota
    ("Insufficient balance", 400, "余额不足"),
    ("您的余额不足以完成本次请求", 402, "余额不足"),
    ("quota exceeded", 429, "余额不足"),  # body wins over the 429 status-only branch
    # Real key failure — 401 AND an auth signal in the body
    ("Invalid API key provided", 401, "API Key 无效"),
    ("api key 无效", 401, "API Key 无效"),
    # Status-only fallbacks (body didn't match any signal)
    ("something opaque", 401, "401（认证失败）"),
    ("not found here", 404, "404"),
    ("rate limited", 429, "429"),
    ("internal error", 500, "HTTP 500"),
]


@pytest.mark.parametrize("body,status,expected_substr", _CASES)
def test_byok_error_message_branches(body: str, status: int, expected_substr: str):
    msg = _byok_error_message(_status_error(body, status), status)
    assert expected_substr in msg


def test_byok_error_message_no_status_is_generic_unavailable():
    # A non-HTTP failure (e.g. a connect error) with no status → generic message.
    msg = _byok_error_message(httpx.ConnectError("connection refused"), None)
    assert "暂时不可用" in msg


def test_byok_error_message_body_signal_beats_status():
    # A 401 whose body actually says "model not found" should report the model
    # problem, not "key invalid" — the whole point of reading the body.
    msg = _byok_error_message(_status_error("model not found", 401), 401)
    assert "模型 ID 不存在" in msg
    assert "API Key 无效" not in msg


def test_byok_error_message_401_without_auth_signal_is_not_key_invalid():
    # 401 but no auth keyword in the body → the softer 401 fallback, never the
    # hard "your key is invalid" claim (which needs an explicit auth signal).
    msg = _byok_error_message(_status_error("upstream hiccup", 401), 401)
    assert "401（认证失败）" in msg
    assert msg != "您的 API Key 无效或已过期，请在个人中心重新配置。"
