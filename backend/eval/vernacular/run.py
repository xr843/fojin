"""对 sample.jsonl 跑三臂（见 GATE.md），输出每条的译文、延迟、finish_reason。

在后端容器内运行（需要平台 LLM key）：

    docker exec -e PYTHONPATH=/tmp:/app fojin-backend python /tmp/run.py /tmp/vern_sample.jsonl > /tmp/vern_out.jsonl
"""

import asyncio
import json
import sys
import time

import httpx

from app.config import settings
from app.services.llm_client import thinking_params

try:  # 评测时 prompt 文件可能还没部署进镜像，放在 /tmp 旁路导入
    from app.services.vernacular_prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_user_message
except ImportError:
    from vernacular_prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_user_message

ARMS = {
    "A": ("deepseek-v4-pro", "off"),
    "B": ("deepseek-v4-pro", None),  # None = 上游默认档
    "C": ("deepseek-v4-flash", "off"),
}
CONCURRENCY = 4


async def call(client: httpx.AsyncClient, sample: dict, arm: str) -> dict:
    model, effort = ARMS[arm]
    extra = thinking_params(model, effort) if effort else {}
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(
                sentence=sample["sentence"], title=sample["title"], translator=sample["translator"],
                before=sample["before"], after=sample["after"],
            )},
        ],
        "temperature": 0.2,
        # 思考臂要给推理留额度，否则推理吃光 max_tokens、正文为空（#1095）
        "max_tokens": 8000 if effort is None else 800,
        "response_format": {"type": "json_object"},
        **extra,
    }
    t0 = time.monotonic()
    out = {"id": sample["id"], "arm": arm, "model": model, "effort": effort or "default", "prompt_version": PROMPT_VERSION}
    try:
        r = await client.post(
            f"{settings.llm_api_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json=body,
        )
        r.raise_for_status()
        data = r.json()
        choice = data["choices"][0]
        out["finish_reason"] = choice.get("finish_reason")
        out["raw"] = choice["message"].get("content") or ""
        out["usage"] = data.get("usage")
        try:
            parsed = json.loads(out["raw"])
            out["translation"] = parsed.get("translation", "")
            out["uncertain"] = bool(parsed.get("uncertain"))
        except json.JSONDecodeError:
            out["translation"] = ""
            out["parse_error"] = True
    except Exception as e:  # 评测记录一切失败
        out["error"] = repr(e)[:300]
    out["latency_s"] = round(time.monotonic() - t0, 2)
    return out


async def main(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        samples = [json.loads(line) for line in f if line.strip()]
    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(timeout=300) as client:

        async def one(s: dict, arm: str) -> dict:
            async with sem:
                return await call(client, s, arm)

        results = await asyncio.gather(*(one(s, a) for s in samples for a in ARMS))
    for r in results:
        print(json.dumps(r, ensure_ascii=False), flush=True)


asyncio.run(main(sys.argv[1]))
