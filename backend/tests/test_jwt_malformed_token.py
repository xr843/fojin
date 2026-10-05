"""未签名的畸形 token 必须被判为「无效」，不能把异常漏成 500。

PyJWT 2.13 在验签之前就 json.loads 解析 header；header 是深度嵌套的 JSON 时抛出
RecursionError——既不是 PyJWTError 也不是 ValueError，穿过 auth 的 except 变成 500。
构造它不需要任何密钥（PYSEC-2026-4142 一族），2.15 起被包成 DecodeError。
"""

import base64
import json

import pytest

from app.core.auth import decode_token_claims, verify_token


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).rstrip(b"=").decode()


DEEP = "[" * 100_000 + "]" * 100_000
HEADER = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}))


@pytest.mark.parametrize(
    "token",
    [
        f"{_b64(DEEP)}.{_b64('{}')}.AAAA",  # 深嵌套 header（2.13 上漏 RecursionError）
        f"{HEADER}.{_b64(DEEP)}.AAAA",  # 深嵌套 payload
        "a.b.c",
        "not-a-jwt",
    ],
    # 默认 id 会是整条 20 万字符的 token，把测试日志撑爆
    ids=["deep-header", "deep-payload", "garbage-segments", "no-dots"],
)
def test_malformed_unsigned_token_is_rejected_not_raised(token):
    assert verify_token(token) is None
    assert decode_token_claims(token) is None
