"""抽样：固定种子从生产库抽 40 句（见 GATE.md）。在后端容器内运行：

    docker exec -e PYTHONPATH=/app fojin-backend python /tmp/sample.py > /tmp/vern_sample.jsonl
"""

import asyncio
import json
import random
import re

from sqlalchemy import text

from app.database import async_session

TEXTS = ["T0235", "T0262", "T0945", "T2008", "T0099", "T1428", "T1558", "T1585", "T1564", "T1911"]
PER_TEXT = 4
SEED = 20261004
SENT = re.compile(r"[^。？！]{20,80}[。？！]")


def _clean(s: str) -> str:
    return re.sub(r"\s+", "", s)


async def main() -> None:
    rng = random.Random(SEED)
    async with async_session() as db:
        for cid in TEXTS:
            row = (await db.execute(
                text("SELECT id, title_zh, translator, dynasty FROM buddhist_texts WHERE cbeta_id = :c ORDER BY id LIMIT 1"),
                {"c": cid},
            )).first()
            if row is None:
                raise SystemExit(f"missing {cid}")
            tid, title, translator, dynasty = row
            juans = [r[0] for r in (await db.execute(
                text("SELECT juan_num FROM text_contents WHERE text_id = :t AND lang = 'lzh' ORDER BY juan_num"),
                {"t": tid},
            ))]
            picked = 0
            tries = 0
            seen: set[tuple[int, int]] = set()
            while picked < PER_TEXT and tries < 200:
                tries += 1
                juan = rng.choice(juans)
                content = (await db.execute(
                    text("SELECT content FROM text_contents WHERE text_id = :t AND juan_num = :j AND lang = 'lzh'"),
                    {"t": tid, "j": juan},
                )).scalar_one()
                flat = _clean(content)
                sents = list(SENT.finditer(flat))
                # 跳过卷首题名/译者行附近（前 60 字）
                sents = [m for m in sents if m.start() > 60]
                if not sents:
                    continue
                m = rng.choice(sents)
                if (juan, m.start()) in seen:
                    continue
                seen.add((juan, m.start()))
                picked += 1
                print(json.dumps({
                    "id": f"{cid}-{picked}",
                    "cbeta_id": cid,
                    "title": title,
                    "translator": translator,
                    "dynasty": dynasty,
                    "juan": juan,
                    "sentence": m.group(0),
                    "before": flat[max(0, m.start() - 150):m.start()],
                    "after": flat[m.end():m.end() + 150],
                }, ensure_ascii=False))


asyncio.run(main())
