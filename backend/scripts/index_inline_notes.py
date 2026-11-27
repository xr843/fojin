"""把夹注（text_inline_notes）写进全文检索索引：每卷文档加一个 notes 字段。

正文 content 字段不动（检索高亮、全藏出处都以它为准）；notes 是本卷全部夹注按原文顺序以「　」相连，
检索时与正文一起搜、权重较低（services/search.py NOTES_BOOST）。

先给索引加 notes 字段映射（只加字段，已有数据不受影响），再按卷部分更新文档（_id = {text_id}_{juan}_lzh，
与 import_content 一致）。幂等：重跑覆盖。库里没有夹注的卷不动。

Usage（一次性容器里跑）：
    python scripts/index_inline_notes.py            # 全部
    python scripts/index_inline_notes.py --work T2128
"""

import argparse
import asyncio
import os
import sys

from elasticsearch.helpers import async_bulk
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.core.elasticsearch import CONTENT_INDEX_NAME, CONTENT_INDEX_SETTINGS, init_es

NOTES_MAPPING = CONTENT_INDEX_SETTINGS["mappings"]["properties"]["notes"]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Index inline notes into the content search index")
    parser.add_argument("--work", type=str, help="Single work (cbeta_id)")
    args = parser.parse_args()

    es = (await init_es()).options(request_timeout=120, retry_on_timeout=True, max_retries=3)
    await es.indices.put_mapping(index=CONTENT_INDEX_NAME, properties={"notes": NOTES_MAPPING})

    engine = create_async_engine(settings.database_url)
    sql = """
        select n.text_id, n.juan_num, string_agg(n.content, '　' order by n.seq)
        from text_inline_notes n join buddhist_texts b on b.id = n.text_id
        {where}
        group by n.text_id, n.juan_num order by n.text_id, n.juan_num
    """.format(where="where b.cbeta_id = :w" if args.work else "")
    async with engine.connect() as conn:
        rows = (await conn.execute(text(sql), {"w": args.work} if args.work else {})).all()
    await engine.dispose()

    def actions():
        for tid, jn, notes in rows:
            yield {"_op_type": "update", "_index": CONTENT_INDEX_NAME, "_id": f"{tid}_{jn}_lzh", "doc": {"notes": notes}}

    ok, errors = await async_bulk(es, actions(), raise_on_error=False, chunk_size=200)
    missing = sum(1 for e in errors if e.get("update", {}).get("status") == 404)
    print(f"juans with notes: {len(rows)}; updated: {ok}; not in index (front matter etc.): {missing}; "
          f"other errors: {len(errors) - missing}")  # fmt: skip
    for e in [e for e in errors if e.get("update", {}).get("status") != 404][:5]:
        print(e)
    await es.close()


if __name__ == "__main__":
    asyncio.run(main())
