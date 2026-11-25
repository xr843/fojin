"""导入 CBETA 里大正藏、卍续藏以外的各藏（嘉興藏、大藏經補編、藏外佛教文獻、漢譯南傳…）。

每部经三步，与 T/X 走同一套程序：经目（buddhist_texts + 标题检索 + 标识）→ 正文（text_contents +
全文检索，import_content.import_work）→ 校勘与行号（import_apparatus.import_work）。

和 import_catalog.py 的区别——这是只增不改的：
- 经目用 ON CONFLICT DO NOTHING：库里已有的经（T/X 的 3,600 多部、标题可能人工改过）一条都不碰；
- 只收 COLLECTIONS 里的藏。印順、太虛、呂澂、演培四套著作权不在 CBETA 的 CC 授权内（NOTICE），
  CBETA 選集里两部现代学者整理/翻译的本子（EXCLUDED_WORKS）也不收；
- 不生成向量（AI 问答的语义检索不覆盖这批经，全文检索与「全藏出处」覆盖）。

磁盘保护：每部经导入前查一次磁盘占用，≥ --max-disk-pct（默认 86%）就停下。Elasticsearch 在 85%
停止分配新分片、90% 迁移分片、95% 把索引置只读；停在这里留出余量。

进度按经记在 data/checkpoints/import_cbeta_canons.done（每行一个经号），中断后重跑自动跳过已完成的。

用法（生产务必在一次性容器里跑，别 exec 进在线容器——导入峰值约 770MB，在线容器上限 1GB）：
    python scripts/import_cbeta_canons.py --xml-dir /data/xml-p5-r2 --plan            # 只列清单，不写库
    python scripts/import_cbeta_canons.py --xml-dir /data/xml-p5-r2 --limit 10         # 试导 10 部
    python scripts/import_cbeta_canons.py --xml-dir /data/xml-p5-r2 --collections J,B
    python scripts/import_cbeta_canons.py --xml-dir /data/xml-p5-r2                    # 全部
"""

import argparse
import asyncio
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import import_apparatus
import import_content
from elasticsearch import AsyncElasticsearch
from import_catalog import create_text_identifiers, index_to_elasticsearch, scan_xml_directory, transform_entry
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.xml_parser import collection_of, find_all_xml_files
from app.models.text import BuddhistText
from app.services.gaiji import build_normalizer

COLLECTIONS = ["J", "B", "ZW", "N", "D", "GA", "G", "L", "P", "C", "I", "K", "F", "A", "ZS", "U", "CC", "S", "GB", "M"]
EXCLUDED_COLLECTIONS = {"T", "X", "Y", "TX", "LC", "YP"}
# CBETA 選集：黃連忠校訂《敦博本六祖壇經校訂全文》、觀空還譯《解深密經疏（補篇）》是现代学者的整理/翻译，
# CBETA 的授权说明没有明说其著作权归属，从严不收。
EXCLUDED_WORKS = {"CC0002", "CC0003"}

DONE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "checkpoints", "import_cbeta_canons.done"
)


def disk_used_pct(path: str) -> float:
    """与 df 同口径：used / (used + 非 root 可用)。"""
    u = shutil.disk_usage(path)
    used = u.total - u.free
    st = os.statvfs(path)
    avail = st.f_bavail * st.f_frsize
    return 100.0 * used / (used + avail)


def load_done() -> set[str]:
    if not os.path.exists(DONE_FILE):
        return set()
    with open(DONE_FILE) as f:
        return {line.strip() for line in f if line.strip()}


def mark_done(cbeta_id: str) -> None:
    os.makedirs(os.path.dirname(DONE_FILE), exist_ok=True)
    with open(DONE_FILE, "a") as f:
        f.write(cbeta_id + "\n")


def plan_records(xml_dir: str, collections: list[str]) -> list[dict]:
    """扫 XML 表头得到经目记录；排除不收的藏与经。"""
    bad = [c for c in collections if c in EXCLUDED_COLLECTIONS]
    if bad:
        raise SystemExit(f"这些藏不在本脚本范围内：{bad}")
    records = []
    for entry in scan_xml_directory(xml_dir, collections):
        rec = transform_entry(entry)
        if not rec or rec["cbeta_id"] in EXCLUDED_WORKS:
            continue
        if collection_of(rec["cbeta_id"]) not in collections:
            continue
        if not find_all_xml_files(rec["cbeta_id"], xml_dir):
            # 经号与文件名对不上（新的编号格式）——宁可报出来也不建一条没有正文的空经目
            print(f"  ⚠️ {rec['cbeta_id']}: 按经号找不到 XML，跳过", flush=True)
            continue
        records.append(rec)
    return records


async def insert_catalog(session_factory, es, records: list[dict]) -> dict[str, int]:
    """只插入库里没有的经；返回本批全部经号 → text_id（含早先已插入的，便于续跑）。"""
    async with session_factory() as session:
        source_id = (await session.execute(text("SELECT id FROM data_sources WHERE code = 'cbeta'"))).scalar_one()
        new_ids: dict[str, int] = {}
        for rec in records:
            row = (
                await session.execute(
                    text("""
                        INSERT INTO buddhist_texts
                            (taisho_id, cbeta_id, title_zh, title_sa, title_bo, title_pi,
                             translator, dynasty, fascicle_count, category, subcategory, cbeta_url, source_id)
                        VALUES
                            (:taisho_id, :cbeta_id, :title_zh, :title_sa, :title_bo, :title_pi,
                             :translator, :dynasty, :fascicle_count, :category, :subcategory, :cbeta_url, :source_id)
                        ON CONFLICT (cbeta_id) DO NOTHING
                        RETURNING id
                    """),
                    {**rec, "source_id": source_id},
                )
            ).fetchone()
            if row:
                new_ids[rec["cbeta_id"]] = row[0]
        await session.commit()
        all_ids = dict(
            (
                await session.execute(
                    select(BuddhistText.cbeta_id, BuddhistText.id).where(
                        BuddhistText.cbeta_id.in_([r["cbeta_id"] for r in records])
                    )
                )
            ).all()
        )
    print(f"  经目：新增 {len(new_ids)} 部，已在库 {len(all_ids) - len(new_ids)} 部", flush=True)
    if new_ids:
        await index_to_elasticsearch(es, [r for r in records if r["cbeta_id"] in new_ids], new_ids)
        async with session_factory() as session:
            await create_text_identifiers(session, new_ids)
    return all_ids


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--xml-dir", required=True)
    ap.add_argument("--collections", default=",".join(COLLECTIONS))
    ap.add_argument("--limit", type=int, default=0, help="最多导入几部（试导用）")
    ap.add_argument("--plan", action="store_true", help="只列清单，不写库")
    ap.add_argument("--max-disk-pct", type=float, default=86.0)
    ap.add_argument("--disk-path", default="/app", help="用来量磁盘占用的路径（与数据库同一块盘）")
    args = ap.parse_args()

    collections = [c.strip() for c in args.collections.split(",") if c.strip()]
    records = plan_records(args.xml_dir, collections)
    by_coll: dict[str, int] = {}
    for r in records:
        c = collection_of(r["cbeta_id"])
        by_coll[c] = by_coll.get(c, 0) + 1
    print(f"计划导入 {len(records)} 部：" + "，".join(f"{c} {n}" for c, n in by_coll.items()), flush=True)
    if args.plan:
        return

    done = load_done()
    todo = [r for r in records if r["cbeta_id"] not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"已完成 {len(done)} 部，本次 {len(todo)} 部；磁盘 {disk_used_pct(args.disk_path):.1f}%", flush=True)
    if not todo:
        return

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    es = AsyncElasticsearch(settings.es_host)
    try:
        ids = await insert_catalog(session_factory, es, todo)
        async with session_factory() as s:
            normalizer = await build_normalizer(s)
        t0 = time.time()
        chars = lines = juans = 0
        for i, rec in enumerate(todo, 1):
            pct = disk_used_pct(args.disk_path)
            if pct >= args.max_disk_pct:
                print(f"🛑 磁盘 {pct:.1f}% ≥ {args.max_disk_pct}%，停在 {rec['cbeta_id']} 之前；已完成的不受影响", flush=True)
                break
            async with session_factory() as session:
                bt = await session.get(BuddhistText, ids[rec["cbeta_id"]])
                n = await import_content.import_work(session, es, bt, args.xml_dir, gaiji_normalizer=normalizer)
                await session.commit()
                await session.refresh(bt)
                counts = await import_apparatus.import_work(session, bt, args.xml_dir)
                juans += n
                chars += bt.content_char_count or 0
                lines += counts.get("line_anchors", 0)
                if counts.get("anchor_juans_skipped"):
                    print(f"  ⚠️ {bt.cbeta_id}: {counts['anchor_juans_skipped']} 卷行号未写（正文不一致）", flush=True)
            mark_done(rec["cbeta_id"])
            if i % 25 == 0 or i == len(todo):
                print(
                    f"  {i}/{len(todo)} 部（{rec['cbeta_id']}），{juans} 卷，{chars / 1e4:.0f} 万字，{lines} 行号，"
                    f"磁盘 {pct:.1f}%，{time.time() - t0:.0f}s",
                    flush=True,
                )
    finally:
        await es.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
