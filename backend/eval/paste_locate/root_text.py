"""贴原文定位 · 修订 5：本经本论会不会被注疏挤出候选（判据见 GATE.md 修订 5）。

同一进程里加载**两份**定位器（旧 = master 版，新 = 待测版，都从文件路径加载），逐条配对跑，
所以两臂共享同一个 ES/库状态，差别只有定位器代码。在一次性容器里运行（不往 /app 写任何东西）：

    docker run --rm --network fojin_default --env-file <env> -v /home/admin/fojin/backend:/app:ro \\
        -v /tmp/pl-eval:/eval -w /app -e PYTHONPATH=/eval:/app:/app/eval/paste_locate fojin-backend \\
        python -u /eval/root_text.py --old /eval/old.py --new /eval/new.py --out /eval/out

子集：
- R / R2 / R3  本经被注疏大量引用（R、R2 开发集 种子 20261016/20261017，R3 留出集 20261018）：从下列本经本论里**按字符位置**随机截 24 字（不按标点切句，与被测的
     「按标点切句、逐句比对」不同源），只留在 ≥2 部**其他**典籍里也逐字出现的片段（ES
     content.nopunct 短语查询判定，与定位器的二元组词袋粗筛不同源）。指标：定位到本经的比例。
- B″ 真经文对照集（independent.sample_b，种子 20261007）。
- A / A′ 世俗名句（independent.SECULAR 80 句 + attribution.A_PRIME 40 句）：注入次数。
- L  延迟与真实回放：90 天全部用户消息，两臂交替先后跑，记录耗时与选中的出处。
**明细含用户原话，只写到 --out 指向的容器外临时目录，不提交。**
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import random
import re
import sys
import time

from sqlalchemy import text as sql_text

from app.core.elasticsearch import init_es
from app.database import async_session

ROOTS = ["T0235", "T0251", "T0262", "T0279", "T0475", "T0945", "T1558", "T1564", "T1585", "T1666"]
R_SEED = 20261016  # 开发集（修订 5）
R2_SEED = 20261017  # 修订 6 的留出集，修订 7 起也是开发集
R3_SEED = 20261018  # 修订 7 的留出集
R_SPAN = 24  # 原文字符数（含标点）
R_MIN_HAN = 16
R_PER_TEXT = 4
R_TRIES_PER_TEXT = 80
R_MIN_OTHER_TEXTS = 2
R_WRAP = ["这段怎么理解：{}", "{} 请解释一下", "请问「{}」是什么意思？"]
CANARY = "凡所有相，皆是虚妄。若见诸相非相，则见如来。这句怎么理解？"
_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w]|_")


def load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclass 需要在 sys.modules 里找到自己的模块
    spec.loader.exec_module(mod)
    return mod


async def run_one(mod, es, msg: str) -> tuple[object, int]:
    t0 = time.monotonic()
    async with async_session() as db:
        loc = await mod.locate_pasted_passage(es, db, msg)
    return loc, round((time.monotonic() - t0) * 1000)


def brief(loc) -> dict | None:
    if loc is None:
        return None
    c = loc.chunk
    return {"text_id": c["text_id"], "cbeta_id": c.get("cbeta_id"), "title": c.get("title_zh"),
            "juan": c["juan_num"], "chunk": c["chunk_index"], "window_han": loc.window_han,
            "texts_with_window": loc.texts_with_window}


async def pair(old, new, es, msg: str, i: int) -> dict:
    # 两臂交替先后，免得 ES/PG 缓存总是偏向后跑的那一臂
    if i % 2 == 0:
        lo, mo = await run_one(old, es, msg)
        ln, mn = await run_one(new, es, msg)
    else:
        ln, mn = await run_one(new, es, msg)
        lo, mo = await run_one(old, es, msg)
    return {"old": brief(lo), "new": brief(ln), "old_ms": mo, "new_ms": mn, "_old": lo, "_new": ln}


async def canary(old, new, es) -> None:
    for name, mod in (("old", old), ("new", new)):
        loc, _ = await run_one(mod, es, CANARY)
        if loc is None:
            raise SystemExit(f"canary failed for {name}: locator is not locating — refusing to produce a meaningless A/B")
        print(f"canary {name}: {loc.chunk.get('cbeta_id')} {loc.chunk.get('title_zh')}", flush=True)


# ── R ───────────────────────────────────────────────────────────────────


async def _carriers(es, span: str) -> dict[int, int]:
    """text_id → 命中卷数：哪些典籍逐字含这段（去标点短语，跨硬换行）。"""
    q = _PUNCT.sub("", span)
    body = {
        "query": {"bool": {"must": [{"match_phrase": {"content.nopunct": {"query": q}}}],
                           "filter": [{"term": {"lang": "lzh"}}]}},
        "size": 0,
        "aggs": {"t": {"terms": {"field": "text_id", "size": 200}}},
    }
    r = await es.search(index="text_contents", body=body, timeout="10s")
    return {b["key"]: b["doc_count"] for b in r["aggregations"]["t"]["buckets"]}


async def sample_r(es, han_count, seed: int = R_SEED) -> tuple[list[dict], dict]:
    rng = random.Random(seed)
    out: list[dict] = []
    stats = {"tried": 0, "root_not_found_by_checker": 0, "too_few_carriers": 0}
    async with async_session() as db:
        for cid in ROOTS:
            tid = (await db.execute(sql_text(
                "SELECT id FROM buddhist_texts WHERE cbeta_id = :c AND lang = 'lzh' ORDER BY id LIMIT 1"),
                {"c": cid})).scalar()
            if tid is None:
                print(f"R: {cid} not in buddhist_texts, skipped", flush=True)
                continue
            juans = [r[0] for r in (await db.execute(sql_text(
                "SELECT juan_num FROM text_contents WHERE text_id = :t AND lang = 'lzh' ORDER BY juan_num"),
                {"t": tid})).all()]
            got = 0
            for _ in range(R_TRIES_PER_TEXT):
                if got >= R_PER_TEXT or not juans:
                    break
                j = rng.choice(juans)
                content = (await db.execute(sql_text(
                    "SELECT content FROM text_contents WHERE text_id = :t AND juan_num = :j AND lang = 'lzh'"),
                    {"t": tid, "j": j})).scalar() or ""
                flat = _WS.sub("", content)
                if len(flat) < R_SPAN + 200:
                    continue
                k = rng.randrange(100, len(flat) - R_SPAN)  # 跳过卷首题名
                span = flat[k:k + R_SPAN]
                if han_count(span) < R_MIN_HAN:
                    continue
                stats["tried"] += 1
                carriers = await _carriers(es, span)
                if tid not in carriers:
                    stats["root_not_found_by_checker"] += 1
                    continue
                others = len(carriers) - 1
                if others < R_MIN_OTHER_TEXTS:
                    stats["too_few_carriers"] += 1
                    continue
                out.append({"root_cbeta": cid, "text_id": tid, "juan": j, "span": span, "other_texts": others})
                got += 1
    return out, stats


async def run_r(old, new, es, seed: int = R_SEED) -> dict:
    items, stats = await sample_r(es, new.han_count, seed)
    dev_seeds = [x for x in (R_SEED, R2_SEED) if x < seed]
    if dev_seeds:  # 留出集剔除与之前各开发集重复的片段
        dev = {(it["text_id"], it["span"]) for d in dev_seeds for it in (await sample_r(es, new.han_count, d))[0]}
        stats["dropped_overlap_with_dev"] = sum((it["text_id"], it["span"]) in dev for it in items)
        items = [it for it in items if (it["text_id"], it["span"]) not in dev]
    rows = []
    for i, it in enumerate(items):
        msg = R_WRAP[i % len(R_WRAP)].format(it["span"])
        p = await pair(old, new, es, msg, i)
        p.pop("_old")
        p.pop("_new")
        rows.append({**it, **p,
                     "old_root": p["old"] is not None and p["old"]["text_id"] == it["text_id"],
                     "new_root": p["new"] is not None and p["new"]["text_id"] == it["text_id"]})
    n = len(rows)
    return {
        "n": n, "sampling": stats,
        "old_root": sum(r["old_root"] for r in rows), "new_root": sum(r["new_root"] for r in rows),
        "old_fired": sum(r["old"] is not None for r in rows), "new_fired": sum(r["new"] is not None for r in rows),
        "old_only": sum(r["old_root"] and not r["new_root"] for r in rows),
        "new_only": sum(r["new_root"] and not r["old_root"] for r in rows),
        "items": rows,
    }


# ── B″ / A / A′ ─────────────────────────────────────────────────────────


async def run_b(old, new, es) -> dict:
    from independent import WRAP_B, sample_b

    async with async_session() as db:
        items = await sample_b(db, 20261007)
    rows = []
    for i, it in enumerate(items):
        msg = WRAP_B[i % len(WRAP_B)].format(it["sentence"])
        p = await pair(old, new, es, msg, i)
        core = new.fast_normalise(it["sentence"])[:12]
        hit = {arm: p[f"_{arm}"] is not None and core in new.fast_normalise(p[f"_{arm}"].chunk["chunk_text"])
               for arm in ("old", "new")}
        p.pop("_old")
        p.pop("_new")
        rows.append({**it, **p, "old_hit": hit["old"], "new_hit": hit["new"]})
    return {"n": len(rows), "old_hit": sum(r["old_hit"] for r in rows), "new_hit": sum(r["new_hit"] for r in rows),
            "items": rows}


async def run_a(old, new, es) -> dict:
    from independent import SECULAR, WRAP_A

    lines = [ln for lst in SECULAR.values() for ln in lst]
    a_prime = [
        "温故而知新，可以为师矣", "学而不思则罔，思而不学则殆", "君子和而不同，小人同而不和", "工欲善其事，必先利其器",
        "敏而好学，不耻下问", "人无远虑，必有近忧", "得道者多助，失道者寡助", "天时不如地利，地利不如人和",
        "大方无隅，大器晚成，大音希声，大象无形", "信言不美，美言不信", "合抱之木，生于毫末", "井蛙不可以语于海者，拘于虚也",
        "穷则变，变则通，通则久", "二人同心，其利断金", "蒹葭苍苍，白露为霜，所谓伊人，在水一方",
        "知我者谓我心忧，不知我者谓我何求", "凡事豫则立，不豫则废", "敖不可长，欲不可从", "鞠躬尽瘁，死而后已",
        "居安思危，思则有备，有备无患", "失之东隅，收之桑榆", "亡羊而补牢，未为迟也", "独在异乡为异客，每逢佳节倍思亲",
        "劝君更尽一杯酒，西出阳关无故人", "沉舟侧畔千帆过，病树前头万木春", "春蚕到死丝方尽，蜡炬成灰泪始干",
        "停车坐爱枫林晚，霜叶红于二月花", "姑苏城外寒山寺，夜半钟声到客船", "曾经沧海难为水，除却巫山不是云",
        "问渠那得清如许？为有源头活水来", "不识庐山真面目，只缘身在此山中", "山重水复疑无路，柳暗花明又一村",
        "夕阳西下，断肠人在天涯", "苛政猛于虎也", "非淡泊无以明志，非宁静无以致远", "其身正，不令而行；其身不正，虽令不从",
        "勿以恶小而为之，勿以善小而不为", "盛年不重来，一日难再晨", "海纳百川，有容乃大", "路漫漫其修远兮，吾将上下而求索",
    ]  # 与 attribution.A_PRIME 相同（不 import，以免拉起整条生成管线）
    wrap_ap = ["「{}」这句话出自哪里？怎么从佛法角度理解？", "我想引用“{}”，请问出处和意思？"]
    msgs = [("A", WRAP_A[i % len(WRAP_A)].format(ln)) for i, ln in enumerate(lines)]
    msgs += [("A′", wrap_ap[i % len(wrap_ap)].format(ln)) for i, ln in enumerate(a_prime)]
    rows = []
    for i, (s, msg) in enumerate(msgs):
        p = await pair(old, new, es, msg, i)
        p.pop("_old")
        p.pop("_new")
        rows.append({"set": s, "msg": msg, **p})
    summ = {}
    for s in ("A", "A′"):
        rs = [r for r in rows if r["set"] == s]
        summ[s] = {
            "n": len(rs), "old_injected": sum(r["old"] is not None for r in rs),
            "new_injected": sum(r["new"] is not None for r in rs),
            "newly_injected": sum(r["new"] is not None and r["old"] is None for r in rs),
            "source_changed": sum(r["new"] is not None and r["old"] is not None
                                  and r["new"]["text_id"] != r["old"]["text_id"] for r in rs),
        }
    return {**summ, "items": rows}


# ── L ───────────────────────────────────────────────────────────────────


def pct(xs: list[int], q: float) -> int:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else 0


async def run_l(old, new, es, days: int, out_dir: str) -> dict:
    async with async_session() as db:
        rows = (await db.execute(sql_text(
            "SELECT id, content FROM chat_messages WHERE role = 'user' "
            f"AND created_at > now() - interval '{int(days)} days' ORDER BY id"))).all()
    recs = []
    with open(os.path.join(out_dir, "L.jsonl"), "w", encoding="utf-8") as f:
        for i, (mid, content) in enumerate(rows):
            p = await pair(old, new, es, content or "", i)
            p.pop("_old")
            p.pop("_new")
            rec = {"id": mid, **p}
            if p["old"] != p["new"]:
                rec["msg_head"] = (content or "")[:160]
            recs.append(rec)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    fired_o = [r["old_ms"] for r in recs if r["old"]]
    fired_n = [r["new_ms"] for r in recs if r["new"]]
    return {
        "n": len(recs),
        "old_p50": pct([r["old_ms"] for r in recs], .5), "old_p95": pct([r["old_ms"] for r in recs], .95),
        "new_p50": pct([r["new_ms"] for r in recs], .5), "new_p95": pct([r["new_ms"] for r in recs], .95),
        "old_fired": len(fired_o), "new_fired": len(fired_n),
        "old_fired_p95": pct(fired_o, .95), "new_fired_p95": pct(fired_n, .95),
        "old_max": max([r["old_ms"] for r in recs] or [0]), "new_max": max([r["new_ms"] for r in recs] or [0]),
        "changed": sum(r["old"] != r["new"] for r in recs),
        "changed_text": sum((r["old"] or {}).get("text_id") != (r["new"] or {}).get("text_id") for r in recs),
    }


async def main(a) -> None:
    old = load(a.old, "pl_old")
    new = load(a.new, "pl_new")
    es = await init_es()
    await canary(old, new, es)
    os.makedirs(a.out, exist_ok=True)
    for name in a.only.split(","):
        if name in ("R2", "R3"):
            res = await run_r(old, new, es, R2_SEED if name == "R2" else R3_SEED)
        else:
            fn = {"R": run_r, "B": run_b, "A": run_a}.get(name)
            res = await (fn(old, new, es) if fn else run_l(old, new, es, a.days, a.out))
        with open(os.path.join(a.out, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        print(name, json.dumps({k: v for k, v in res.items() if k != "items"}, ensure_ascii=False), flush=True)
    await es.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True, help="旧版 passage_locator.py 路径")
    ap.add_argument("--new", required=True, help="新版 passage_locator.py 路径")
    ap.add_argument("--out", default="/tmp/pl-eval")
    ap.add_argument("--only", default="R3,R2,R,B,A,L")
    ap.add_argument("--days", type=int, default=90)
    asyncio.run(main(ap.parse_args()))
