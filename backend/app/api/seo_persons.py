"""Server-rendered SEO landing pages for KG ``person`` entities.

The frontend SPA does not have a ``/persons/:id`` route, so visitors land
here exclusively from search engines or external citations. We render a
self-contained, content-rich HTML document that does not boot the React
bundle — Googlebot gets a fully-resolved page on the first fetch, real
users get a fast static-feeling landing page that links into the SPA
through the knowledge graph and related-text links.

There are 43,916 person entities (as of 2026-05); this is the largest
single content surface FoJin can offer search engines, and it has been
fully invisible up to this point.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.seo import _escape_meta_value, public_base_url
from app.database import get_db
from app.models.knowledge_graph import KGEntity, KGRelation
from app.models.text import BuddhistText

logger = logging.getLogger(__name__)
router = APIRouter(tags=["seo"])

_RELATED_TEXTS_LIMIT = 30
_RELATED_PERSONS_LIMIT = 12
_DUPLICATE_CANDIDATES_LIMIT = 50


def _person_display_dates(props: dict | None) -> str:
    """Best-effort birth/death years from KGEntity.properties."""
    if not isinstance(props, dict):
        return ""
    birth = props.get("birth_year") or props.get("birth")
    death = props.get("death_year") or props.get("death")
    if birth and death:
        return f"（{birth}–{death}）"
    if birth:
        return f"（{birth}–）"
    if death:
        return f"（–{death}）"
    return ""


def _person_dynasty(props: dict | None) -> str:
    if not isinstance(props, dict):
        return ""
    return (props.get("dynasty") or props.get("era") or "").strip()


def _person_nationality(props: dict | None) -> str:
    if not isinstance(props, dict):
        return ""
    return (props.get("nationality") or props.get("country") or "").strip()


# Mirror of frontend AUTHORITY_MAP in PersonPage.tsx — keep both in sync
# when adding a new authority. Sharing one source-of-truth would require
# either a JSON file both sides read (over-engineered) or a code-gen step
# (more moving parts than 6 lines deserve). The cost is symmetric: 6
# lines here, 6 lines there.
_AUTHORITY_URI_BUILDERS: dict[str, object] = {
    "wikidata": lambda i: f"https://www.wikidata.org/wiki/{i}",
    "dila": lambda i: f"https://authority.dila.edu.tw/person/?fromInner={i}",
    "bdrc": lambda i: f"https://library.bdrc.io/show/bdr:{i}",
    "viaf": lambda i: f"https://viaf.org/viaf/{i}",
    "loc": lambda i: f"https://id.loc.gov/authorities/names/{i}",
}


def _same_as_uris(external_ids: dict | None) -> list[str]:
    """Build owl:sameAs URIs from external_ids — Wave 2.4 SSR parity.

    The frontend SPA route /person/:id already renders sameAs via
    react-helmet (PR #674). The SSR route /persons/:id previously
    exposed only schema.org identifier[] — Googlebot/crawlers that
    don't execute JS thus missed the sameAs linkage. This restores
    parity: same payload across both routes.
    """
    if not isinstance(external_ids, dict):
        return []
    out: list[str] = []
    for key, value in external_ids.items():
        if not value:
            continue
        builder = _AUTHORITY_URI_BUILDERS.get(key)
        if builder is None:
            continue
        out.append(builder(str(value)))
    return out


def _build_person_jsonld(entity: KGEntity, *, canonical: str) -> dict:
    name = (entity.name_zh or "").strip() or f"佛教人物 #{entity.id}"
    payload: dict = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": name,
        "url": canonical,
    }
    alt = [
        entity.name_en,
        entity.name_sa,
        entity.name_pi,
        entity.name_bo,
    ]
    alt = [a for a in alt if a]
    if alt:
        payload["alternateName"] = alt
    if entity.description:
        payload["description"] = entity.description[:500]
    props = entity.properties if isinstance(entity.properties, dict) else {}
    nat = _person_nationality(props)
    if nat:
        payload["nationality"] = nat
    if entity.external_ids:
        ids = []
        if isinstance(entity.external_ids, dict):
            for key, value in entity.external_ids.items():
                if value:
                    ids.append({"@type": "PropertyValue", "propertyID": key, "value": str(value)})
        if ids:
            payload["identifier"] = ids
        same_as = _same_as_uris(entity.external_ids)
        if same_as:
            payload["sameAs"] = same_as
    return payload


async def _find_canonical_person_id(db: AsyncSession, entity: KGEntity) -> int:
    """Resolve the canonical id for entities sharing (name_zh, entity_type).

    kg_entities has real duplicate person rows — e.g. 6 separate rows all
    named 法藏 — each getting its own self-referencing /persons/{id} SEO
    page. That splits search ranking signal across N URLs instead of
    consolidating it on one (keyword cannibalization). There is no
    merge/redirect table for this: the only existing dedup (migration 0159)
    covers just the subset of persons carrying an external ``dila`` id.

    Canonical-selection rule, applied deterministically so every duplicate
    resolves to the same winner regardless of which one a crawler fetches:

      1. Longest ``description`` wins (more content = the page worth ranking).
      2. Ties — including "all empty" — broken by the smallest ``id``.

    The candidate lookup is an exact-equality match on ``name_zh`` (indexed:
    ix_kg_entities_name_zh from migration 0006) filtered by entity_type, so
    it stays a cheap index scan even though it runs on every request.
    Candidates are capped at _DUPLICATE_CANDIDATES_LIMIT, ordered by id
    ascending, to bound the pathological case of a name shared by an
    unexpectedly large number of rows. Measured on prod (2026-08): the
    largest person cluster is 18 rows, and 50+ distinct names have 7 or
    more — so duplication is widespread, but the cap still carries ~2.7x
    headroom over the worst case. Because candidates arrive in
    ascending-id order, Python's max() — which keeps the first winner on a
    tie — implements rule 2 for free.
    """
    if not entity.name_zh:
        return entity.id

    result = await db.execute(
        select(KGEntity.id, KGEntity.description)
        .where(KGEntity.name_zh == entity.name_zh)
        .where(KGEntity.entity_type == entity.entity_type)
        .order_by(KGEntity.id.asc())
        .limit(_DUPLICATE_CANDIDATES_LIMIT)
    )
    candidates = result.all()
    if len(candidates) <= 1:
        return entity.id
    winner = max(candidates, key=lambda row: len(row.description or ""))
    return winner.id


async def _fetch_person_related(
    db: AsyncSession, entity_id: int
) -> tuple[list[BuddhistText], list[KGEntity]]:
    """Pull texts the person translated/authored + KG-linked persons."""
    rel_rows = await db.execute(
        select(KGRelation).where(
            or_(
                KGRelation.subject_id == entity_id,
                KGRelation.object_id == entity_id,
            )
        )
    )
    relations = rel_rows.scalars().all()

    related_person_ids: set[int] = set()
    for r in relations:
        other = r.object_id if r.subject_id == entity_id else r.subject_id
        related_person_ids.add(other)

    # KGRelation doesn't link directly to BuddhistText, so fall back to the
    # translator-name LIKE match. Imperfect (homonyms exist) but the only
    # signal we have without expanding the relation schema.
    person = await db.get(KGEntity, entity_id)
    name_zh = (person.name_zh or "").strip() if person else ""

    texts: list[BuddhistText] = []
    if name_zh:
        text_match = await db.execute(
            select(BuddhistText)
            .where(BuddhistText.translator.ilike(f"%{name_zh}%"))
            .order_by(BuddhistText.id.asc())
            .limit(_RELATED_TEXTS_LIMIT)
        )
        texts = list(text_match.scalars().all())

    related_persons: list[KGEntity] = []
    if related_person_ids:
        ent_q = await db.execute(
            select(KGEntity)
            .where(KGEntity.id.in_(related_person_ids))
            .where(KGEntity.entity_type == "person")
            .limit(_RELATED_PERSONS_LIMIT)
        )
        related_persons = list(ent_q.scalars().all())

    return texts, related_persons


def _render_person_html(
    entity: KGEntity,
    *,
    related_texts: list[BuddhistText],
    related_persons: list[KGEntity],
    canonical: str,
    base_url: str,
) -> str:
    name_zh = (entity.name_zh or "").strip() or f"佛教人物 #{entity.id}"
    props = entity.properties if isinstance(entity.properties, dict) else {}
    dates = _person_display_dates(props)
    dynasty = _person_dynasty(props)
    nationality = _person_nationality(props)
    description = (entity.description or "").strip()

    title = f"{name_zh}{dates} — 佛教人物 | 佛津 FoJin"

    desc_meta_bits = [name_zh]
    if dynasty:
        desc_meta_bits.append(dynasty)
    if nationality:
        desc_meta_bits.append(nationality)
    if description:
        desc_meta_bits.append(description[:80])
    else:
        desc_meta_bits.append("佛教高僧人物档案")
    desc_meta_bits.append("佛津 FoJin 提供佛教人物时空数据库与原典溯源。")
    description_meta = "，".join(desc_meta_bits)
    description_meta = description_meta[:300]

    alt_names = [n for n in (entity.name_en, entity.name_sa, entity.name_pi, entity.name_bo) if n]

    jsonld = json.dumps(
        _build_person_jsonld(entity, canonical=canonical),
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    breadcrumb = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "佛津 FoJin", "item": base_url},
                {"@type": "ListItem", "position": 2, "name": "佛教人物", "item": f"{base_url}/kg"},
                {"@type": "ListItem", "position": 3, "name": name_zh, "item": canonical},
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")

    safe_title = _escape_meta_value(title)
    safe_desc = _escape_meta_value(description_meta)
    safe_canonical = _escape_meta_value(canonical)
    safe_name = _escape_meta_value(name_zh)

    css = (
        "body{font-family:-apple-system,Segoe UI,PingFang SC,sans-serif;"
        "max-width:760px;margin:24px auto;padding:0 16px;line-height:1.7;color:#222;}"
        "h1{font-size:1.8rem;margin:0 0 8px;}"
        "h2{font-size:1.15rem;margin:24px 0 8px;border-bottom:1px solid #ddd;padding-bottom:4px;}"
        ".meta{color:#666;font-size:0.95rem;margin:0 0 12px;}"
        ".alt{color:#888;font-size:0.9rem;margin:0 0 16px;}"
        "ul{padding-left:20px;}li{margin:4px 0;}"
        "a{color:#8b2500;text-decoration:none;}a:hover{text-decoration:underline;}"
        "footer{margin-top:32px;color:#888;font-size:0.85rem;border-top:1px solid #eee;padding-top:12px;}"
    )

    parts = [
        "<!doctype html>",
        '<html lang="zh-Hans">',
        "<head>",
        '<meta charset="utf-8" />',
        '<meta name="viewport" content="width=device-width,initial-scale=1" />',
        f"<title>{safe_title}</title>",
        f'<meta name="description" content="{safe_desc}" />',
        '<meta name="robots" content="index, follow" />',
        f'<link rel="canonical" href="{safe_canonical}" />',
        '<meta property="og:type" content="profile" />',
        f'<meta property="og:title" content="{safe_title}" />',
        f'<meta property="og:description" content="{safe_desc}" />',
        f'<meta property="og:url" content="{safe_canonical}" />',
        '<meta property="og:site_name" content="佛津 FoJin" />',
        '<meta name="twitter:card" content="summary" />',
        f"<style>{css}</style>",
        f'<script type="application/ld+json">{jsonld}</script>',
        f'<script type="application/ld+json">{breadcrumb}</script>',
        "</head>",
        "<body>",
        f"<h1>{safe_name}{_escape_meta_value(dates)}</h1>",
    ]

    meta_line_bits = []
    if dynasty:
        meta_line_bits.append(_escape_meta_value(dynasty))
    if nationality:
        meta_line_bits.append(_escape_meta_value(nationality))
    if entity.entity_type:
        meta_line_bits.append(_escape_meta_value(entity.entity_type))
    if meta_line_bits:
        parts.append('<p class="meta">' + " · ".join(meta_line_bits) + "</p>")

    if alt_names:
        parts.append(
            '<p class="alt">' + " / ".join(_escape_meta_value(n) for n in alt_names) + "</p>"
        )

    if description:
        parts.append(f"<p>{_escape_meta_value(description)}</p>")

    if related_texts:
        parts.append("<h2>相关佛典</h2><ul>")
        for t in related_texts[:_RELATED_TEXTS_LIMIT]:
            t_title = _escape_meta_value((t.title_zh or "").strip() or f"佛典 #{t.id}")
            cbeta = f" (CBETA {_escape_meta_value(t.cbeta_id)})" if t.cbeta_id else ""
            parts.append(
                f'<li><a href="{base_url}/texts/{t.id}">《{t_title}》</a>{cbeta}</li>'
            )
        parts.append("</ul>")

    if related_persons:
        parts.append("<h2>相关人物</h2><ul>")
        for p in related_persons:
            p_name = _escape_meta_value((p.name_zh or "").strip() or f"人物 #{p.id}")
            parts.append(f'<li><a href="{base_url}/persons/{p.id}">{p_name}</a></li>')
        parts.append("</ul>")

    parts.append(
        f'<p><a href="{base_url}/kg">浏览全部佛教人物 »</a> · '
        f'<a href="{base_url}/map">人物地图</a></p>'
    )
    parts.append(
        '<footer>数据来源：DILA 人物时空规范资料库、Wikidata、维基百科、BDRC。'
        '佛津 FoJin 是开源佛教数字人文聚合平台。</footer>'
    )
    parts.append("</body></html>")
    return "".join(parts)


@router.api_route(
    "/persons/{person_id}",
    methods=["GET", "HEAD"],
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def person_seo_html(
    person_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    entity = await db.get(KGEntity, person_id)
    if entity is None or entity.entity_type != "person":
        raise HTTPException(status_code=404, detail="person not found")

    base_url = public_base_url(request)

    try:
        canonical_id = await _find_canonical_person_id(db, entity)
    except Exception as e:  # canonical resolution is best-effort; self-reference is always safe
        logger.warning("canonical person lookup failed for %s: %s", entity.id, e)
        canonical_id = entity.id
    # og:url / JSON-LD url / breadcrumb item below all reuse this same value —
    # deliberate: og:url's own spec calls it "the canonical URL of your
    # object", and a JSON-LD url that disagreed with <link rel="canonical">
    # would be a self-contradictory signal. The page BODY still renders this
    # entity's own content (name, description, related texts/persons) below —
    # only the crawler-facing URL signals move to the winning duplicate.
    canonical = f"{base_url}/persons/{canonical_id}"

    try:
        related_texts, related_persons = await _fetch_person_related(db, entity.id)
    except Exception as e:  # related blocks are best-effort
        logger.warning("person related fetch failed for %s: %s", entity.id, e)
        related_texts, related_persons = [], []

    html = _render_person_html(
        entity,
        related_texts=related_texts,
        related_persons=related_persons,
        canonical=canonical,
        base_url=base_url,
    )
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=3600"})
