"""Alibaba Cloud SMS service for sending verification codes."""

import hashlib
import hmac
import json
import urllib.parse
import uuid
from base64 import b64encode
from datetime import UTC, datetime

import httpx

from app.config import settings

ALIYUN_SMS_ENDPOINT = "https://dysmsapi.aliyuncs.com"


def _sign(params: dict, access_key_secret: str) -> str:
    """Compute Alibaba Cloud API signature (SignatureMethod=HMAC-SHA1)."""
    sorted_params = sorted(params.items())
    query = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
        for k, v in sorted_params
    )
    string_to_sign = f"GET&%2F&{urllib.parse.quote(query, safe='')}"
    h = hmac.new(
        f"{access_key_secret}&".encode(),
        string_to_sign.encode(),
        hashlib.sha1,
    )
    return b64encode(h.digest()).decode("utf-8")


async def send_sms(phone: str, code: str) -> None:
    """Send a verification code SMS via Alibaba Cloud."""
    params = {
        "AccessKeyId": settings.aliyun_sms_access_key_id,
        "Action": "SendSms",
        "Format": "JSON",
        "PhoneNumbers": phone,
        "RegionId": "cn-hangzhou",
        "SignName": settings.aliyun_sms_sign_name,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": str(uuid.uuid4()),
        "SignatureVersion": "1.0",
        "TemplateCode": settings.aliyun_sms_template_code,
        "TemplateParam": json.dumps({"code": code}),
        "Timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Version": "2017-05-25",
    }
    params["Signature"] = _sign(params, settings.aliyun_sms_access_key_secret)

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(ALIYUN_SMS_ENDPOINT, params=params)
        resp.raise_for_status()
        result = resp.json()
        if result.get("Code") != "OK":
            raise RuntimeError(f"Aliyun SMS error: {result.get('Message', 'unknown')}")
