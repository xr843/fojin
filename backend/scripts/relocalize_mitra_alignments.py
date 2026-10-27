#!/usr/bin/env python3
"""重建过向量的卷，把 mitra_alignments 的块编号重新对到新分块上。

repair_stale_embeddings.py 重建一卷会重新切块、重新编号，而 mitra_alignments
按 (text_id, juan_num, chunk_index) 指向分块。原本的做法是拿 MITRA 原始 TSV 重新
导入（import_mitra_alignments.py），但生产上那份数据已不在。好在每行都存了
``zh_text``（MITRA 的汉文句子），所以不需要原始数据：用导入脚本**同一套**
``_load_chunks`` / ``_locate`` 在新分块里重新定位——先在本卷找，句子够长且全经
唯一时才跨卷——再改写 chunk_index（跨卷命中时连 juan_num 一起改）。

找不到的行不删，原样保留并计数：它们本来就指向错标的旧块，重建前后都不可靠，
交给人看比悄悄删掉更安全。

用法（容器内）::

    python scripts/relocalize_mitra_alignments.py --pairs-file /data/juan-scan2/pairs.json --dry-run
    python scripts/relocalize_mitra_alignments.py --pairs-file /data/juan-scan2/pairs.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.import_mitra_alignments import _load_chunks, _locate, _norm
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings


def plan_updates(rows, juan_of_row, tj_index, t_index):
    """[(row_id, new_chunk_index, new_juan)] for rows whose location changed, plus a tally.

    ``rows`` are (id, juan_num, chunk_index, zh_text). Pure so it can be tested
    without a database.
    """
    updates, tally = [], Counter()
    for rid, juan, cidx, zh in rows:
        new_c, new_j, scope = _locate(_norm(zh or ""), juan_of_row(juan), tj_index, t_index)
        if new_c is None:
            tally["unlocated"] += 1
            continue
        if (new_c, new_j) == (cidx, juan):
            tally["unchanged"] += 1
            continue
        tally["moved_juan" if new_j != juan else "moved_chunk"] += 1
        updates.append((rid, new_c, new_j))
    return updates, tally


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs-file", required=True, help="pairs.json from scan_embedding_juan_labels.py")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    with open(args.pairs_file) as f:
        pairs = json.load(f)
    by_text: dict[int, set[int]] = {}
    for t, j, *_ in pairs:
        by_text.setdefault(int(t), set()).add(int(j))

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    total = Counter()
    try:
        async with engine.connect() as conn:
            for tid, juans in sorted(by_text.items()):
                taisho = (
                    await conn.execute(sql_text("SELECT taisho_id FROM buddhist_texts WHERE id = :t"), {"t": tid})
                ).scalar()
                rows = (
                    await conn.execute(
                        sql_text(
                            "SELECT id, juan_num, chunk_index, zh_text FROM mitra_alignments "
                            "WHERE text_id = :t AND juan_num = ANY(:j)"
                        ),
                        {"t": tid, "j": sorted(juans)},
                    )
                ).fetchall()
                if not rows or not taisho:
                    await conn.rollback()
                    continue
                text_id, tj_index, t_index = await _load_chunks(conn, taisho)
                await conn.rollback()  # CPU work below must not hold a transaction (60s idle limit)
                if text_id != tid:
                    print(f"  text {tid}: taisho {taisho} resolves to text {text_id}, skipped", flush=True)
                    total["skipped_text"] += 1
                    continue
                updates, tally = plan_updates(rows, lambda j: j, tj_index, t_index)
                total.update(tally)
                total["rows"] += len(rows)
                print(f"  text {tid} {taisho}: {len(rows)} rows {dict(tally)}", flush=True)
                if updates and not args.dry_run:
                    await conn.execute(
                        sql_text("UPDATE mitra_alignments SET chunk_index = :c, juan_num = :j WHERE id = :i"),
                        [{"i": i, "c": c, "j": j} for i, c, j in updates],
                    )
                    await conn.commit()
    finally:
        await engine.dispose()
    print(f"DONE{' (dry-run)' if args.dry_run else ''}: {dict(total)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
