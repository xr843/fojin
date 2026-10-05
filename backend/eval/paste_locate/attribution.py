"""修订 3 · A′：世俗名句的「出处张冠李戴」答案层评测。

旧臂与新臂用同一份**新版**检索代码（rag_retrieval + passage_locator），旧臂只把
ENABLE_PASTE_LOCATE 关掉，所以两臂唯一的差别就是定位器（含上下文里的标注）。
上线前在容器里旁路加载：把 /tmp/passage_locator.py 注册成 app.services.passage_locator，
再以 rag_retrieval_new 的名字加载 /tmp/rag_retrieval.py。

    docker exec -e PYTHONPATH=/tmp:/app -w /app fojin-backend python -u /tmp/attribution.py --out /tmp/attr.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys

import httpx
from eval.run_eval import EVAL_LLM_TIMEOUT_S, build_eval_llm_body

from app.core.elasticsearch import init_es
from app.database import async_session
from app.services.chat import _build_llm_messages, _resolve_llm_config


def _load_new_pipeline():
    try:
        import app.services.passage_locator  # noqa: F401 — 已部署则直接用
        from app.services import rag_retrieval as r
        return r
    except ImportError:
        import passage_locator

        from app.config import settings

        # 新配置项尚未部署进生产镜像；旁路加载时补上（取值无关紧要，两臂各自显式设开关）
        if not hasattr(settings, "enable_paste_locate"):
            settings.__dict__["enable_paste_locate"] = True
        sys.modules["app.services.passage_locator"] = passage_locator
        spec = importlib.util.spec_from_file_location("rag_retrieval_new", "/tmp/rag_retrieval.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


R = _load_new_pipeline()

A_PRIME = [
    "温故而知新，可以为师矣", "学而不思则罔，思而不学则殆", "君子和而不同，小人同而不和", "工欲善其事，必先利其器",
    "敏而好学，不耻下问", "人无远虑，必有近忧", "得道者多助，失道者寡助", "天时不如地利，地利不如人和",
    "大方无隅，大器晚成，大音希声，大象无形", "信言不美，美言不信", "合抱之木，生于毫末", "井蛙不可以语于海者，拘于虚也",
    "穷则变，变则通，通则久", "二人同心，其利断金", "蒹葭苍苍，白露为霜，所谓伊人，在水一方", "知我者谓我心忧，不知我者谓我何求",
    "凡事豫则立，不豫则废", "敖不可长，欲不可从", "鞠躬尽瘁，死而后已", "居安思危，思则有备，有备无患",
    "失之东隅，收之桑榆", "亡羊而补牢，未为迟也", "独在异乡为异客，每逢佳节倍思亲", "劝君更尽一杯酒，西出阳关无故人",
    "沉舟侧畔千帆过，病树前头万木春", "春蚕到死丝方尽，蜡炬成灰泪始干", "停车坐爱枫林晚，霜叶红于二月花", "姑苏城外寒山寺，夜半钟声到客船",
    "曾经沧海难为水，除却巫山不是云", "问渠那得清如许？为有源头活水来", "不识庐山真面目，只缘身在此山中", "山重水复疑无路，柳暗花明又一村",
    "夕阳西下，断肠人在天涯", "苛政猛于虎也", "非淡泊无以明志，非宁静无以致远", "其身正，不令而行；其身不正，虽令不从",
    "勿以恶小而为之，勿以善小而不为", "盛年不重来，一日难再晨", "海纳百川，有容乃大", "路漫漫其修远兮，吾将上下而求索",
]
WRAP = ["「{}」这句话出自哪里？怎么从佛法角度理解？", "我想引用“{}”，请问出处和意思？"]


async def _answer(client, context: str, question: str) -> str:
    api_url, api_key, model, _, _ = _resolve_llm_config(None)
    try:
        r = await client.post(
            f"{api_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=build_eval_llm_body(model, _build_llm_messages([], context, question), 0.0),
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"] or ""
    except Exception as e:  # 评测记录一切失败
        return f"[ERROR] {e!r}"[:300]


async def one(client, sem, i: int, line: str) -> dict:
    q = WRAP[i % len(WRAP)].format(line)
    async with sem:
        R.ENABLE_PASTE_LOCATE = False
        async with async_session() as s:
            old_src, old_ctx = await R.retrieve_rag_context(s, q)
        R.ENABLE_PASTE_LOCATE = True
        async with async_session() as s:
            new_src, new_ctx = await R.retrieve_rag_context(s, q)
        located = "[用户原文定位]" in new_ctx
        old_ans, new_ans = await asyncio.gather(_answer(client, old_ctx, q), _answer(client, new_ctx, q))
    return {
        "line": line, "question": q, "located": located,
        "located_title": new_src[0].title_zh if located and new_src else None,
        "old_titles": [x.title_zh for x in old_src], "new_titles": [x.title_zh for x in new_src],
        "old_answer": old_ans, "new_answer": new_ans,
    }


CANARY = "凡所有相，皆是虚妄。若见诸相非相，则见如来。这句怎么理解？"


async def ensure_locator_alive() -> None:
    """金丝雀：定位器失败会按设计静默降级成旧管线——在评测里那等于两臂毫无差别，
    产出一份看似正常、实则作废的结果（2026-10-05 第一次跑 A′ 就是这样：ES 未初始化，
    40 条全部没定位）。开跑前用一句已知原文确认它真的在工作，否则中止。"""
    await init_es()
    R.ENABLE_PASTE_LOCATE = True
    async with async_session() as s:
        _, ctx = await R.retrieve_rag_context(s, CANARY)
    if "[用户原文定位]" not in ctx:
        raise SystemExit("canary failed: locator is not injecting — refusing to produce a meaningless A/B")


async def main(out: str) -> None:
    await ensure_locator_alive()
    sem = asyncio.Semaphore(3)
    async with httpx.AsyncClient(timeout=EVAL_LLM_TIMEOUT_S) as client:
        rows = await asyncio.gather(*(one(client, sem, i, ln) for i, ln in enumerate(A_PRIME)))
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/attr.jsonl")
    asyncio.run(main(ap.parse_args().out))
