"""Seed the Buddhist concept network into the knowledge graph.

Two jobs, both idempotent:

  1. Expand the ``concept`` entity set — the graph shipped with only 18
     core concepts; this adds 27 more standard doctrinal concepts.
  2. Author concept-to-concept relations — before this script there were
     zero concept↔concept edges (the existing ``associated_with`` edges
     all linked concepts to texts/persons). The concept *network* was a
     set of isolated nodes; this connects them.

The relations below are standard, textbook-level Buddhist doctrine
(e.g. 缘起↔空性, 四圣谛↔八正道). They are inserted as ``associated_with``
edges tagged ``source='seed:concept_network'`` so they are auditable and
distinguishable from auto-extracted or catalogue-sourced edges — the
same provenance convention as the existing ``seed:lineage`` edges.

Idempotent: concepts are matched by ``name_zh``; a relation is skipped
if an ``associated_with`` edge already joins the pair in either
direction. Re-running inserts nothing new.

Usage (from backend/):
    python scripts/seed_concept_network.py --dry-run   # preview, rolls back
    python scripts/seed_concept_network.py             # commit
"""

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

SOURCE = "seed:concept_network"
PREDICATE = "associated_with"

# 27 additional core Buddhist concepts. The graph already carries 18
# (缘起, 四圣谛, 八正道, 空性, 唯识, 佛性, 般若, 涅槃, 菩提, 三法印,
# 十二因缘, 六波罗蜜, 中道, 三学, 五蕴, 禅定, 业, 轮回).
NEW_CONCEPTS: list[dict[str, str]] = [
    {"name_zh": "苦", "name_en": "Duḥkha", "name_sa": "Duḥkha",
     "description": "四圣谛之首，指生命中无所不在的不圆满、逼迫与不安；佛教修行的起点即对苦的如实认知。"},
    {"name_zh": "无常", "name_en": "Impermanence", "name_sa": "Anitya",
     "description": "三法印之一，一切有为法刹那生灭、迁流不住，无有恒常自体。"},
    {"name_zh": "无我", "name_en": "Non-Self", "name_sa": "Anātman",
     "description": "三法印之一，五蕴和合的身心之中并无独立常住的主宰自我。"},
    {"name_zh": "四念处", "name_en": "Four Foundations of Mindfulness", "name_sa": "Smṛtyupasthāna",
     "description": "观身、受、心、法四种念住，是原始佛教与禅修的根本观行法门。"},
    {"name_zh": "三宝", "name_en": "Three Jewels", "name_sa": "Triratna",
     "description": "佛、法、僧三者，为佛教徒皈依的对象与信仰核心。"},
    {"name_zh": "菩提心", "name_en": "Bodhicitta", "name_sa": "Bodhicitta",
     "description": "大乘行者为利益一切众生而誓愿成佛之心，是菩萨道的根本发起。"},
    {"name_zh": "如来藏", "name_en": "Tathāgatagarbha", "name_sa": "Tathāgatagarbha",
     "description": "众生本具的如来性德，为成佛的内在依据，与佛性义相通。"},
    {"name_zh": "法身", "name_en": "Dharma Body", "name_sa": "Dharmakāya",
     "description": "佛的真理之身，离一切相而遍一切处，为三身之根本。"},
    {"name_zh": "十地", "name_en": "Ten Bhūmis", "name_sa": "Daśabhūmi",
     "description": "菩萨修行证悟的十个阶位，从欢喜地至法云地，渐次圆满。"},
    {"name_zh": "四无量心", "name_en": "Four Immeasurables", "name_sa": "Apramāṇa",
     "description": "慈、悲、喜、舍四种广大平等的心量，普缘一切众生。"},
    {"name_zh": "戒", "name_en": "Moral Discipline", "name_sa": "Śīla",
     "description": "三学之一，防非止恶、摄护身口意的行为规范与德行基础。"},
    {"name_zh": "烦恼", "name_en": "Afflictions", "name_sa": "Kleśa",
     "description": "扰恼身心、障碍解脱的贪、嗔、痴等心理染污。"},
    {"name_zh": "无明", "name_en": "Ignorance", "name_sa": "Avidyā",
     "description": "对缘起实相的根本无知，是十二因缘流转的源头。"},
    {"name_zh": "解脱", "name_en": "Liberation", "name_sa": "Vimokṣa",
     "description": "脱离烦恼系缚与生死轮回的自在境地。"},
    {"name_zh": "真如", "name_en": "Suchness", "name_sa": "Tathatā",
     "description": "诸法离妄之真实体性，常住不变、平等一味的实相。"},
    {"name_zh": "二谛", "name_en": "Two Truths", "name_sa": "Satyadvaya",
     "description": "世俗谛与胜义谛，是中观判别言说与实相的根本框架。"},
    {"name_zh": "阿赖耶识", "name_en": "Storehouse Consciousness", "name_sa": "Ālayavijñāna",
     "description": "唯识学所立第八识，含藏一切种子，为诸法生起的根本依。"},
    {"name_zh": "三自性", "name_en": "Three Natures", "name_sa": "Trisvabhāva",
     "description": "唯识学的遍计所执、依他起、圆成实三种存在性质。"},
    {"name_zh": "止观", "name_en": "Calm and Insight", "name_sa": "Śamatha-vipaśyanā",
     "description": "止息散乱与观照实相并修的禅法纲领。"},
    {"name_zh": "四摄", "name_en": "Four Means of Embracing", "name_sa": "Saṃgrahavastu",
     "description": "布施、爱语、利行、同事四种摄受众生的方法。"},
    {"name_zh": "三身", "name_en": "Three Bodies", "name_sa": "Trikāya",
     "description": "佛的法身、报身、化身三种身相。"},
    {"name_zh": "方便", "name_en": "Skillful Means", "name_sa": "Upāya",
     "description": "菩萨随顺众生根机而善巧施设的教化手段。"},
    {"name_zh": "回向", "name_en": "Dedication of Merit", "name_sa": "Pariṇāmanā",
     "description": "将所修善根功德转向菩提与众生的修行行持。"},
    {"name_zh": "皈依", "name_en": "Taking Refuge", "name_sa": "Śaraṇagamana",
     "description": "归投三宝、确立佛教徒身份的根本仪轨与信心。"},
    {"name_zh": "念佛", "name_en": "Buddha-Recollection", "name_sa": "Buddhānusmṛti",
     "description": "忆念、称念佛之名号功德的修行法门，为净土宗的核心行持。"},
    {"name_zh": "出离心", "name_en": "Renunciation", "name_sa": "Niḥsaraṇa",
     "description": "厌离生死轮回、欣求解脱的意愿，为修道的根本动力。"},
    {"name_zh": "法界", "name_en": "Dharma Realm", "name_sa": "Dharmadhātu",
     "description": "一切诸法的本然界域，华严宗以之统摄事事无碍的圆融实相。"},
]

# Concept-to-concept doctrinal relations. Each pair becomes one
# undirected `associated_with` edge. Standard doctrine only.
RELATIONS: list[tuple[str, str]] = [
    # 缘起 / 十二因缘 / 三法印
    ("缘起", "十二因缘"), ("缘起", "空性"), ("缘起", "中道"),
    ("缘起", "无常"), ("缘起", "无我"), ("缘起", "业"),
    ("十二因缘", "无明"), ("十二因缘", "轮回"), ("十二因缘", "业"), ("十二因缘", "苦"),
    ("三法印", "无常"), ("三法印", "无我"), ("三法印", "涅槃"), ("三法印", "苦"),
    # 苦 / 四圣谛 / 五蕴
    ("苦", "四圣谛"), ("苦", "无常"), ("苦", "五蕴"),
    ("四圣谛", "八正道"), ("四圣谛", "涅槃"),
    ("五蕴", "无我"), ("五蕴", "空性"),
    # 道品 / 三学
    ("八正道", "三学"), ("八正道", "四念处"),
    ("三学", "戒"), ("三学", "禅定"), ("三学", "般若"),
    ("戒", "皈依"), ("皈依", "三宝"), ("三宝", "菩提心"),
    ("禅定", "止观"), ("四念处", "止观"), ("止观", "般若"), ("念佛", "禅定"),
    # 烦恼 / 解脱 / 轮回
    ("烦恼", "无明"), ("烦恼", "轮回"), ("无明", "轮回"), ("业", "轮回"),
    ("轮回", "涅槃"), ("轮回", "解脱"), ("解脱", "涅槃"), ("解脱", "烦恼"),
    ("出离心", "解脱"), ("出离心", "轮回"),
    # 般若 / 空 / 中道 / 二谛 / 真如
    ("般若", "空性"), ("般若", "中道"), ("般若", "六波罗蜜"),
    ("空性", "中道"), ("空性", "二谛"), ("空性", "真如"),
    ("中道", "二谛"), ("真如", "法界"), ("真如", "法身"), ("真如", "如来藏"),
    # 菩提 / 菩提心 / 六度 / 十地
    ("菩提心", "菩提"), ("菩提心", "六波罗蜜"), ("菩提心", "四无量心"),
    ("菩提", "涅槃"), ("菩提", "佛性"), ("菩提", "法身"),
    ("六波罗蜜", "禅定"), ("六波罗蜜", "戒"), ("六波罗蜜", "方便"), ("六波罗蜜", "回向"),
    ("十地", "六波罗蜜"), ("十地", "菩提"),
    ("四摄", "菩提心"), ("四摄", "方便"), ("回向", "菩提心"),
    # 佛性 / 如来藏 / 法身 / 三身
    ("佛性", "如来藏"), ("佛性", "涅槃"), ("法身", "三身"), ("如来藏", "法身"),
    # 唯识
    ("唯识", "阿赖耶识"), ("唯识", "三自性"), ("唯识", "空性"),
    ("阿赖耶识", "三自性"), ("三自性", "空性"),
    # 法界
    ("法界", "法身"),
]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the concept network.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview counts without committing.")
    args = parser.parse_args()

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        rows = (await session.execute(text(
            "SELECT id, name_zh FROM kg_entities WHERE entity_type = 'concept'"
        ))).fetchall()
        name_to_id: dict[str, int] = {r[1]: r[0] for r in rows}
        print(f"existing concepts: {len(name_to_id)}")

        # ── 1. Insert new concept entities ──
        inserted_concepts = 0
        for c in NEW_CONCEPTS:
            if c["name_zh"] in name_to_id:
                continue
            inserted_concepts += 1
            if args.dry_run:
                # Placeholder id so relation resolution still works in preview.
                name_to_id[c["name_zh"]] = -inserted_concepts
                continue
            res = await session.execute(text("""
                INSERT INTO kg_entities
                    (entity_type, name_zh, name_en, name_sa, description,
                     source_tier, source_version, ingested_at)
                VALUES
                    ('concept', :zh, :en, :sa, :desc,
                     'curated', :ver, :now)
                RETURNING id
            """), {"zh": c["name_zh"], "en": c["name_en"], "sa": c["name_sa"],
                   "desc": c["description"], "ver": SOURCE, "now": datetime.now(UTC)})
            name_to_id[c["name_zh"]] = res.scalar_one()
        print(f"new concepts {'(dry-run) ' if args.dry_run else ''}inserted: {inserted_concepts}")

        # ── 2. Insert concept↔concept relations ──
        inserted_rels = 0
        missing: list[tuple[str, str]] = []
        for a, b in RELATIONS:
            ida, idb = name_to_id.get(a), name_to_id.get(b)
            if ida is None or idb is None:
                missing.append((a, b))
                continue
            exists = (await session.execute(text("""
                SELECT 1 FROM kg_relations
                WHERE predicate = :pred
                  AND ((subject_id = :a AND object_id = :b)
                    OR (subject_id = :b AND object_id = :a))
                LIMIT 1
            """), {"pred": PREDICATE, "a": ida, "b": idb})).first()
            if exists:
                continue
            inserted_rels += 1
            if args.dry_run:
                continue
            await session.execute(text("""
                INSERT INTO kg_relations
                    (subject_id, predicate, object_id, source, confidence)
                VALUES (:a, :pred, :b, :src, 1.0)
            """), {"a": ida, "pred": PREDICATE, "b": idb, "src": SOURCE})
        print(f"relations {'(dry-run) ' if args.dry_run else ''}inserted: {inserted_rels}")
        if missing:
            print(f"WARNING: {len(missing)} relation(s) skipped — concept not found: {missing}")

        if args.dry_run:
            await session.rollback()
            print("dry-run: rolled back, no changes written")
        else:
            await session.commit()
            print("committed")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
