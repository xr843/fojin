import csv
import io
import json
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_optional_user
from app.database import get_db
from app.models.text import BuddhistText
from app.models.knowledge_graph import KGEntity, KGRelation
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/exports", tags=["exports"])

# Batch size for streaming exports
BATCH_SIZE = 500


@router.get("/stats")
async def export_stats(db: AsyncSession = Depends(get_db)):
    """返回各类数据的总量，供前端展示。"""
    text_count = (await db.execute(select(func.count(BuddhistText.id)))).scalar() or 0
    entity_count = (await db.execute(select(func.count(KGEntity.id)))).scalar() or 0
    relation_count = (await db.execute(select(func.count(KGRelation.id)))).scalar() or 0
    return {
        "texts": text_count,
        "kg_entities": entity_count,
        "kg_relations": relation_count,
    }


@router.get("/metadata.csv")
async def export_metadata_csv(
    dynasty: str | None = Query(None, description="按朝代筛选"),
    category: str | None = Query(None, description="按分类筛选"),
    lang: str | None = Query(None, description="按语言筛选"),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """导出佛典元数据为 CSV 格式，支持分批流式输出。"""
    stmt = select(BuddhistText).order_by(BuddhistText.id)
    if dynasty:
        stmt = stmt.where(BuddhistText.dynasty == dynasty)
    if category:
        stmt = stmt.where(BuddhistText.category == category)
    if lang:
        stmt = stmt.where(BuddhistText.lang == lang)

    async def generate_csv():
        # Write CSV header
        header_buf = io.StringIO()
        writer = csv.writer(header_buf)
        writer.writerow([
            "id", "cbeta_id", "taisho_id", "title_zh", "title_sa", "title_bo",
            "title_pi", "translator", "dynasty", "fascicle_count", "category",
            "subcategory", "lang",
        ])
        yield header_buf.getvalue()

        # Stream rows in batches
        offset = 0
        while True:
            batch_stmt = stmt.offset(offset).limit(BATCH_SIZE)
            result = await db.execute(batch_stmt)
            texts = result.scalars().all()
            if not texts:
                break

            buf = io.StringIO()
            writer = csv.writer(buf)
            for t in texts:
                writer.writerow([
                    t.id, t.cbeta_id, t.taisho_id, t.title_zh,
                    t.title_sa or "", t.title_bo or "", t.title_pi or "",
                    t.translator or "", t.dynasty or "",
                    t.fascicle_count or "", t.category or "",
                    t.subcategory or "", t.lang or "lzh",
                ])
            yield buf.getvalue()
            offset += BATCH_SIZE

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=fojin_metadata.csv"},
    )


@router.get("/kg.json")
async def export_kg_json(
    entity_type: str | None = Query(None, description="按实体类型筛选"),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """导出知识图谱为 JSON 格式，分批流式输出。"""
    entity_stmt = select(KGEntity).order_by(KGEntity.id)
    if entity_type:
        entity_stmt = entity_stmt.where(KGEntity.entity_type == entity_type)

    async def generate_json():
        yield '{\n  "entities": [\n'

        # Stream entities
        offset = 0
        first = True
        entity_ids: set[int] = set()
        while True:
            result = await db.execute(entity_stmt.offset(offset).limit(BATCH_SIZE))
            entities = result.scalars().all()
            if not entities:
                break
            for e in entities:
                entity_ids.add(e.id)
                obj = {
                    "id": e.id,
                    "entity_type": e.entity_type,
                    "name_zh": e.name_zh,
                    "name_sa": e.name_sa,
                    "name_pi": e.name_pi,
                    "name_bo": e.name_bo,
                    "name_en": e.name_en,
                    "description": e.description,
                    "properties": e.properties,
                    "external_ids": e.external_ids,
                    "text_id": e.text_id,
                }
                prefix = "    " if first else ",\n    "
                first = False
                yield prefix + json.dumps(obj, ensure_ascii=False)
            offset += BATCH_SIZE

        yield '\n  ],\n  "relations": [\n'

        # Stream relations; when filtering by entity_type, only include
        # relations where BOTH endpoints are in the exported entity set.
        rel_stmt = select(KGRelation).order_by(KGRelation.id)
        skip_relations = False
        if entity_type:
            if entity_ids:
                rel_stmt = rel_stmt.where(
                    KGRelation.subject_id.in_(entity_ids),
                    KGRelation.object_id.in_(entity_ids),
                )
            else:
                # No entities matched the filter — skip relations entirely
                skip_relations = True

        offset = 0
        first = True
        if not skip_relations:
            while True:
                result = await db.execute(rel_stmt.offset(offset).limit(BATCH_SIZE))
                relations = result.scalars().all()
                if not relations:
                    break
                for r in relations:
                    obj = {
                        "id": r.id,
                        "subject_id": r.subject_id,
                        "predicate": r.predicate,
                        "object_id": r.object_id,
                        "confidence": r.confidence,
                        "properties": r.properties,
                        "source": r.source,
                    }
                    prefix = "    " if first else ",\n    "
                    first = False
                    yield prefix + json.dumps(obj, ensure_ascii=False)
                offset += BATCH_SIZE

        yield '\n  ]\n}\n'

    return StreamingResponse(
        generate_json(),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=fojin_kg.json"},
    )


@router.get("/kg.jsonld")
async def export_kg_jsonld(
    entity_type: str | None = Query(None, description="按实体类型筛选"),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """导出知识图谱为 JSON-LD 格式，使用标准语义词汇。"""
    entity_stmt = select(KGEntity).order_by(KGEntity.id)
    if entity_type:
        entity_stmt = entity_stmt.where(KGEntity.entity_type == entity_type)

    async def generate_jsonld():
        context = {
            "@context": {
                "skos": "http://www.w3.org/2004/02/skos/core#",
                "dcterms": "http://purl.org/dc/terms/",
                "schema": "http://schema.org/",
                "owl": "http://www.w3.org/2002/07/owl#",
                "fojin": "https://fojin.org/ontology/",
                "prefLabel": "skos:prefLabel",
                "altLabel": "skos:altLabel",
                "description": "dcterms:description",
                "sameAs": "owl:sameAs",
            },
            "@graph": [],
        }
        # Emit context header as partial JSON; we'll stream @graph items
        header = json.dumps(context, ensure_ascii=False, indent=2)
        # Remove the closing `]` and `}` so we can append items
        # Output: everything up to the empty @graph array opening
        yield '{\n'
        yield '  "@context": ' + json.dumps(context["@context"], ensure_ascii=False, indent=4) + ',\n'
        yield '  "@graph": [\n'

        offset = 0
        first = True

        # Stream entities
        entity_ids: set[int] = set()
        while True:
            result = await db.execute(entity_stmt.offset(offset).limit(BATCH_SIZE))
            entities = result.scalars().all()
            if not entities:
                break
            for e in entities:
                entity_ids.add(e.id)
                node: dict = {
                    "@id": f"fojin:entity/{e.id}",
                    "@type": f"fojin:{e.entity_type}",
                    "prefLabel": {"@value": e.name_zh, "@language": "zh"},
                }
                # Multilingual labels
                if e.name_sa:
                    node.setdefault("altLabel", []).append({"@value": e.name_sa, "@language": "sa"})
                if e.name_pi:
                    node.setdefault("altLabel", []).append({"@value": e.name_pi, "@language": "pi"})
                if e.name_bo:
                    node.setdefault("altLabel", []).append({"@value": e.name_bo, "@language": "bo"})
                if e.name_en:
                    node.setdefault("altLabel", []).append({"@value": e.name_en, "@language": "en"})
                if e.description:
                    node["description"] = e.description
                if e.text_id:
                    node["fojin:linkedText"] = e.text_id
                if e.external_ids:
                    # Map external IDs to owl:sameAs
                    same_as = [v for v in e.external_ids.values() if isinstance(v, str) and v.startswith("http")]
                    if same_as:
                        node["sameAs"] = [{"@id": uri} for uri in same_as]

                prefix = "    " if first else ",\n    "
                first = False
                yield prefix + json.dumps(node, ensure_ascii=False)
            offset += BATCH_SIZE

        # Stream relations — same filtering logic as kg.json
        rel_stmt = select(KGRelation).order_by(KGRelation.id)
        skip_relations = False
        if entity_type:
            if entity_ids:
                rel_stmt = rel_stmt.where(
                    KGRelation.subject_id.in_(entity_ids),
                    KGRelation.object_id.in_(entity_ids),
                )
            else:
                skip_relations = True

        offset = 0
        if not skip_relations:
            while True:
                result = await db.execute(rel_stmt.offset(offset).limit(BATCH_SIZE))
                relations = result.scalars().all()
                if not relations:
                    break
                for r in relations:
                    node = {
                        "@id": f"fojin:relation/{r.id}",
                        "@type": "fojin:Relation",
                        "fojin:subject": {"@id": f"fojin:entity/{r.subject_id}"},
                        "fojin:predicate": r.predicate,
                        "fojin:object": {"@id": f"fojin:entity/{r.object_id}"},
                        "fojin:confidence": r.confidence,
                    }
                    if r.source:
                        node["dcterms:source"] = r.source
                    prefix = "    " if first else ",\n    "
                    first = False
                    yield prefix + json.dumps(node, ensure_ascii=False)
                offset += BATCH_SIZE

        yield '\n  ]\n}\n'

    return StreamingResponse(
        generate_jsonld(),
        media_type="application/ld+json; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=fojin_kg.jsonld"},
    )
