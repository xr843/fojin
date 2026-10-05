"""贴原文定位：两个独立集（修订 2，见 GATE.md）。在后端容器内运行：

    docker exec -e PYTHONPATH=/tmp:/app -w /app fojin-backend python -u /tmp/independent.py

A 世俗对抗集：80 句非佛典名句，按类别构造，期望定位器一句都不注入（≤1）。
B 真经文对照集：从语料按藏随机抽 80 句正文（修订 4 起不排除引号里的句子），期望 ≥90% 定位到包含该句的检索块。
"""

from __future__ import annotations

import asyncio
import json
import random
import re

from sqlalchemy import text as sql_text

from app.core.elasticsearch import init_es
from app.database import async_session

try:
    from app.services.passage_locator import fast_normalise, han_count, locate_pasted_passage
except ImportError:  # 上线前评测：从 /tmp 旁路导入
    from passage_locator import fast_normalise, han_count, locate_pasted_passage

SECULAR = {
    "论孟学庸": [
        "学而时习之，不亦说乎？有朋自远方来，不亦乐乎", "己所不欲，勿施于人", "三人行，必有我师焉",
        "知之为知之，不知为不知，是知也", "君子坦荡荡，小人长戚戚", "岁寒，然后知松柏之后凋也",
        "老吾老以及人之老，幼吾幼以及人之幼", "穷则独善其身，达则兼善天下", "富贵不能淫，贫贱不能移，威武不能屈",
        "大学之道，在明明德，在亲民，在止于至善", "喜怒哀乐之未发谓之中，发而皆中节谓之和", "博学之，审问之，慎思之，明辨之，笃行之",
    ],
    "老庄": [
        "道可道，非常道；名可名，非常名", "上善若水，水善利万物而不争", "天下难事，必作于易；天下大事，必作于细",
        "千里之行，始于足下", "祸兮福之所倚，福兮祸之所伏", "知人者智，自知者明",
        "北冥有鱼，其名为鲲，鲲之大，不知其几千里也", "吾生也有涯，而知也无涯", "天地与我并生，而万物与我为一",
        "子非鱼，安知鱼之乐", "相濡以沫，不如相忘于江湖",
    ],
    "易诗书礼": [
        "天行健，君子以自强不息", "地势坤，君子以厚德载物", "积善之家，必有余庆；积不善之家，必有余殃",
        "仰以观于天文，俯以察于地理，是故知幽明之故", "关关雎鸠，在河之洲，窈窕淑女，君子好逑", "他山之石，可以攻玉",
        "如切如磋，如琢如磨", "满招损，谦受益", "玉不琢，不成器；人不学，不知道", "大道之行也，天下为公",
        "苟日新，日日新，又日新",
    ],
    "史传": [
        "燕雀安知鸿鹄之志哉", "王侯将相宁有种乎", "人固有一死，或重于泰山，或轻于鸿毛",
        "运筹帷幄之中，决胜千里之外", "桃李不言，下自成蹊", "前事之不忘，后事之师",
        "多行不义必自毙", "一鼓作气，再而衰，三而竭", "皮之不存，毛将焉附",
    ],
    "唐诗": [
        "床前明月光，疑是地上霜，举头望明月，低头思故乡", "人生自古谁无死，留取丹心照汗青", "安得广厦千万间，大庇天下寒士俱欢颜",
        "春眠不觉晓，处处闻啼鸟，夜来风雨声，花落知多少", "海内存知己，天涯若比邻", "月落乌啼霜满天，江枫渔火对愁眠",
        "行到水穷处，坐看云起时", "空山不见人，但闻人语响", "会当凌绝顶，一览众山小", "国破山河在，城春草木深",
        "白日依山尽，黄河入海流，欲穷千里目，更上一层楼", "野火烧不尽，春风吹又生", "两岸猿声啼不住，轻舟已过万重山",
    ],
    "宋词元曲": [
        "明月几时有，把酒问青天", "人有悲欢离合，月有阴晴圆缺，此事古难全", "大江东去，浪淘尽，千古风流人物",
        "众里寻他千百度，蓦然回首，那人却在灯火阑珊处", "枯藤老树昏鸦，小桥流水人家", "寻寻觅觅，冷冷清清，凄凄惨惨戚戚",
        "衣带渐宽终不悔，为伊消得人憔悴", "落花人独立，微雨燕双飞", "竹杖芒鞋轻胜马，谁怕？一蓑烟雨任平生",
    ],
    "古文与典故": [
        "先天下之忧而忧，后天下之乐而乐", "落霞与孤鹜齐飞，秋水共长天一色", "醉翁之意不在酒，在乎山水之间也",
        "采菊东篱下，悠然见南山", "问君何能尔？心远地自偏", "山不在高，有仙则名；水不在深，有龙则灵",
        "古之学者必有师，师者，所以传道受业解惑也", "業精于勤，荒于嬉；行成于思，毁于随", "不以物喜，不以己悲",
        "出淤泥而不染，濯清涟而不妖", "夫天地者，万物之逆旅；光阴者，百代之过客", "一年之计在于春，一日之计在于晨",
        "少壮不努力，老大徒伤悲", "近朱者赤，近墨者黑", "有志者事竟成",
    ],
}
WRAP_A = [
    "我想在文章里引用「{}」，这句话怎么理解？能和佛法会通吗？",
    "{}——这句话从佛教角度怎么看？",
    "请问“{}”出自哪里？是什么意思？",
]
WRAP_B = ["{} 这句是什么意思？", "请帮我消文：{}", "「{}」这段怎么理解？"]
SPLIT = re.compile(r"(?<=[。！？])")
CANON_QUOTA = {"T": 50, "X": 22, "J": 4, "A": 2, "K": 2}  # 大致按语料构成


async def run_a(es) -> dict:
    lines = [(cat, ln) for cat, lst in SECULAR.items() for ln in lst]
    out = []
    for i, (cat, ln) in enumerate(lines):
        msg = WRAP_A[i % len(WRAP_A)].format(ln)
        async with async_session() as db:
            loc = await locate_pasted_passage(es, db, msg)
        out.append({"cat": cat, "line": ln, "injected": None if loc is None else f"{loc.chunk.get('cbeta_id')} {loc.chunk.get('title_zh')}"})
    return {"n": len(out), "injected": sum(1 for o in out if o["injected"]), "items": out}


async def sample_b(db, seed: int) -> list[dict]:
    rng = random.Random(seed)
    picked: list[dict] = []
    for prefix, quota in CANON_QUOTA.items():
        ids = [r[0] for r in (await db.execute(sql_text(
            "SELECT bt.id FROM buddhist_texts bt WHERE bt.lang='lzh' AND bt.cbeta_id LIKE :p "
            "AND EXISTS (SELECT 1 FROM text_embeddings te WHERE te.text_id = bt.id)"), {"p": prefix + "%"})).all()]
        tries = 0
        got = 0
        while got < quota and tries < quota * 20 and ids:
            tries += 1
            tid = rng.choice(ids)
            juans = [r[0] for r in (await db.execute(sql_text(
                "SELECT juan_num FROM text_contents WHERE text_id=:t AND lang='lzh'"), {"t": tid})).all()]
            if not juans:
                continue
            j = rng.choice(juans)
            content = (await db.execute(sql_text(
                "SELECT content FROM text_contents WHERE text_id=:t AND juan_num=:j"), {"t": tid, "j": j})).scalar() or ""
            flat = re.sub(r"\s+", "", content)
            sents = [s for s in SPLIT.split(flat) if 12 <= han_count(s) <= 60]
            rng.shuffle(sents)
            for s in sents[:5]:
                k = flat.find(s)
                if k > 60:  # 修订 4：不再排除引号里的句子（经文对白都在「」里）
                    picked.append({"text_id": tid, "juan": j, "sentence": s})
                    got += 1
                    break
    return picked


async def run_b(es, seed: int) -> dict:
    async with async_session() as db:
        items = await sample_b(db, seed)
    out = []
    for i, it in enumerate(items):
        msg = WRAP_B[i % len(WRAP_B)].format(it["sentence"])
        async with async_session() as db:
            loc = await locate_pasted_passage(es, db, msg)
        hit = False
        if loc is not None:
            raw = loc.chunk["chunk_text"]
            core = fast_normalise(it["sentence"])
            hit = core[: min(len(core), 12)] in fast_normalise(raw)  # 定位到的块至少含这句的前 12 字
        out.append({**it, "located": None if loc is None else f"{loc.chunk.get('cbeta_id')} {loc.chunk.get('title_zh')}",
                    "same_text": loc is not None and loc.chunk["text_id"] == it["text_id"], "hit": hit})
    return {"n": len(out), "hit": sum(o["hit"] for o in out), "same_text": sum(o["same_text"] for o in out), "items": out}


async def main(only: str, seed: int) -> None:
    es = await init_es()
    out = {}
    if only in ("A", "all"):
        out["A"] = await run_a(es)
    if only in ("B", "all"):
        out["B"] = await run_b(es, seed=seed)
    await es.close()
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="all", choices=["A", "B", "all"])
    ap.add_argument("--seed", type=int, default=20261005)
    a = ap.parse_args()
    asyncio.run(main(a.only, a.seed))
