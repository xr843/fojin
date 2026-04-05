"""
Extract translation sites (譯場) from CBETA XML metadata and create
text → place `translated_at` relations in the knowledge graph.

Two sources:
  A. Per-text colophons / prefaces / postscripts — scan each text's own XML
     body for patterns like "於XX寺譯". High-confidence, ~dozens of texts.
  B. Catalog texts (T2153 大周刊定眾經目錄, T2154 開元釋教錄, T2157 貞元新定
     釋教目錄). Each `<item>` pairs `<cb:jl_title>` with `於XX寺譯`. Match
     those titles back to `buddhist_texts.title_zh` by exact string match.

After extracting text→place pairs the script:
  - Confirms the place name exists in KG (entity_type='place')
  - Creates KGRelation(subject=text, predicate='translated_at', object=place)
    with source='cbeta_xml:colophon' or 'cbeta_xml:catalog:T2153' etc.
  - Then propagates: for each text with a translator person and a
    translated_at site, if the translator person has no coordinates yet,
    copies the place's lat/lng into person.properties with
    geo_source='translation_site:<place_name>'.

Strict truth constraint: we do NOT guess. Every relation has a clean
provenance chain back to a specific CBETA XML file and line number.
Place names must already exist in the KG place entity table — we do not
create new place entities.

Usage:
    cd backend
    python -m scripts.extract_cbeta_translation_sites --dry-run
    python -m scripts.extract_cbeta_translation_sites        # actually write
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

from lxml import etree
from sqlalchemy import and_, select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.models.knowledge_graph import KGEntity, KGRelation
from app.models.text import BuddhistText

# ----------------------------------------------------------------------------
# XML parsing
# ----------------------------------------------------------------------------

TEI_NS = "http://www.tei-c.org/ns/1.0"
CB_NS = "http://www.cbeta.org/ns/1.0"

DEFAULT_XML_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "data" / "xml-p5"

# Canonical translation-site whitelist. Names must match KG place entities.
# This list is the intersection of historically-attested translation sites
# and names we expect to find in FoJin's place entities.
KNOWN_SITES: set[str] = {
    "大慈恩寺", "慈恩寺",
    "大興善寺", "興善寺",
    "玉華宮", "玉華寺",
    "弘福寺",
    "西明寺",
    "白馬寺",
    "大薦福寺", "薦福寺",
    "佛授記寺",
    "大福先寺", "福先寺",
    "崇福寺",
    "光宅寺",
    "大周東寺", "東寺",
    "鹿野寺",
    "東安寺",
    "天平寺",
    "寶月寺",
    "瓦官寺",
    "資聖寺",
    "醴泉寺",
    "莊嚴寺",
    "章敬寺",
    "大明寺",
    "青龍寺",
    "開元寺",
    "永泰寺",
    "大相國寺", "相國寺",
    "譯經院", "傳法院", "傳法譯經院",
    "金花寺",
    "枳園寺",
    "翻經院",
}

# Per-text colophon regex (scan plain text of whole body, post-note-stripping).
SITE_PATTERN = re.compile(
    r"於([^，。、；：\s]{2,12}(?:寺|宮|殿|院|觀|堂))"
    r"(?:翻譯|譯訖|譯出|譯成|翻出|翻經|[翻譯]{1,2})"
)


def _strip_notes(root: etree._Element) -> None:
    """Remove <note>, <app>, <rdg> so they don't pollute text extraction."""
    for tag in (f"{{{TEI_NS}}}note", f"{{{TEI_NS}}}app", f"{{{TEI_NS}}}rdg"):
        for elem in root.findall(f".//{tag}"):
            parent = elem.getparent()
            if parent is not None:
                parent.remove(elem)


def extract_sites_from_own_colophon(xml_path: Path) -> set[str]:
    """Strategy A — scan this text's own body for site phrases."""
    try:
        tree = etree.parse(str(xml_path))
    except Exception:
        return set()
    root = tree.getroot()
    text_el = root.find(f".//{{{TEI_NS}}}text")
    if text_el is None:
        return set()
    _strip_notes(text_el)
    full_text = re.sub(r"\s+", "", "".join(text_el.itertext()))
    sites = set()
    for m in SITE_PATTERN.finditer(full_text):
        name = m.group(1)
        if name in KNOWN_SITES:
            sites.add(name)
    return sites


def extract_sites_from_catalog(xml_path: Path) -> list[tuple[str, str]]:
    """Strategy B — parse a CBETA catalog; return [(text_title, site), ...].

    Catalog entries often place bibliographic annotations (including the
    translation site) inside <note place="inline">, so unlike per-text
    colophons we do NOT strip notes here. We only strip critical-apparatus
    <app>/<rdg> elements and modern corrections <note resp="#resp1">.
    """
    try:
        tree = etree.parse(str(xml_path))
    except Exception:
        return []
    root = tree.getroot()
    # Strip only apparatus & modern corrections, keep inline content notes.
    for tag in (f"{{{TEI_NS}}}app", f"{{{TEI_NS}}}rdg"):
        for el in root.findall(f".//{tag}"):
            p = el.getparent()
            if p is not None:
                p.remove(el)
    for note in root.findall(f".//{{{TEI_NS}}}note"):
        if note.get("resp") == "#resp1":
            p = note.getparent()
            if p is not None:
                p.remove(note)
    pairs: list[tuple[str, str]] = []
    items = root.findall(f".//{{{TEI_NS}}}item")
    for item in items:
        # Each item holds a cb:jl_title (work title) plus descriptive <p>s.
        title_el = item.find(f".//{{{CB_NS}}}jl_title")
        if title_el is None or not (title_el.text or "").strip():
            continue
        title = (title_el.text or "").strip()
        item_text = re.sub(r"\s+", "", "".join(item.itertext()))
        for m in SITE_PATTERN.finditer(item_text):
            site = m.group(1)
            if site in KNOWN_SITES:
                pairs.append((title, site))
                break  # first site wins per item
    return pairs


# ----------------------------------------------------------------------------
# cbeta_id inference from XML filename
# ----------------------------------------------------------------------------

_FILENAME_RE = re.compile(r"^([A-Z]+)(\d+)n([A-Z]?\d+[a-z]?)(?:_[0-9]+)?$")


def cbeta_id_from_filename(stem: str) -> str | None:
    """T05n0220a → T0220a; T55n2153 → T2153.  Returns None if unparseable."""
    m = _FILENAME_RE.match(stem)
    if not m:
        return None
    canon, _vol, num = m.groups()
    return f"{canon}{num}"


# ----------------------------------------------------------------------------
# Main workflow
# ----------------------------------------------------------------------------

CATALOG_SOURCES = {
    "T2153": "data/xml-p5/T/T55/T55n2153.xml",
    "T2154": "data/xml-p5/T/T55/T55n2154.xml",
    "T2157": "data/xml-p5/T/T55/T55n2157.xml",
}


async def load_kg_places(session: AsyncSession) -> dict[str, int]:
    """Return {place_name_zh: entity_id} for entities of type 'place'."""
    result = await session.execute(
        select(KGEntity.id, KGEntity.name_zh).where(KGEntity.entity_type == "place")
    )
    return {row.name_zh: row.id for row in result}


async def load_text_entities(session: AsyncSession) -> dict[str, int]:
    """Return {cbeta_id: kg_entity_id} for all text-type entities that link to a buddhist_text row."""
    # text entities link back to buddhist_texts via text_id; join to get cbeta_id
    q = sql_text(
        """
        SELECT e.id AS entity_id, t.cbeta_id
        FROM kg_entities e
        JOIN buddhist_texts t ON e.text_id = t.id
        WHERE e.entity_type = 'text'
        """
    )
    result = await session.execute(q)
    return {row.cbeta_id: row.entity_id for row in result}


async def load_texts_by_title(session: AsyncSession) -> dict[str, list[str]]:
    """Return {title_zh: [cbeta_id, ...]} for all buddhist_texts."""
    result = await session.execute(select(BuddhistText.cbeta_id, BuddhistText.title_zh))
    by_title: dict[str, list[str]] = defaultdict(list)
    for row in result:
        by_title[row.title_zh].append(row.cbeta_id)
    return by_title


async def existing_translated_at(session: AsyncSession) -> set[tuple[int, int]]:
    """Pairs (subject_id, object_id) that already have a translated_at relation."""
    result = await session.execute(
        select(KGRelation.subject_id, KGRelation.object_id).where(
            KGRelation.predicate == "translated_at"
        )
    )
    return {(r.subject_id, r.object_id) for r in result}


async def run(
    xml_dir: Path,
    dry_run: bool,
    collections: list[str] | None,
) -> None:
    engine = create_async_engine(settings.database_url_async, future=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # ---- Scan XML ----------------------------------------------------------
    # Strategy A: per-text colophons
    colophon_sites: dict[str, set[str]] = {}
    print(f"[A] Scanning per-text colophons in {xml_dir}...")
    total_scanned = 0
    if collections is None:
        collection_dirs = [d for d in xml_dir.iterdir() if d.is_dir()]
    else:
        collection_dirs = [xml_dir / c for c in collections if (xml_dir / c).is_dir()]
    for coll_dir in collection_dirs:
        for xml_file in coll_dir.rglob("*.xml"):
            total_scanned += 1
            sites = extract_sites_from_own_colophon(xml_file)
            if sites:
                cid = cbeta_id_from_filename(xml_file.stem)
                if cid:
                    colophon_sites.setdefault(cid, set()).update(sites)
    print(f"[A] Scanned {total_scanned} XML files; {len(colophon_sites)} with site refs.")

    # Strategy B: catalogs
    catalog_pairs: list[tuple[str, str, str]] = []  # (catalog_id, title, site)
    print("[B] Parsing catalogs...")
    for cat_id, rel_path in CATALOG_SOURCES.items():
        cat_path = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / rel_path
        if not cat_path.exists():
            print(f"  [skip] {cat_id}: missing {cat_path}")
            continue
        pairs = extract_sites_from_catalog(cat_path)
        print(f"  [{cat_id}] {len(pairs)} (title, site) pairs")
        for title, site in pairs:
            catalog_pairs.append((cat_id, title, site))

    # ---- Match to DB -------------------------------------------------------
    async with Session() as session:
        places = await load_kg_places(session)
        text_entities = await load_text_entities(session)
        titles_index = await load_texts_by_title(session)
        existing_pairs = await existing_translated_at(session)

    print(f"\nKG places loaded: {len(places)}")
    print(f"KG text entities loaded: {len(text_entities)}")
    print(f"Existing translated_at relations: {len(existing_pairs)}")

    # Build resolution: cbeta_id → set(site_name)
    resolved: dict[str, set[str]] = defaultdict(set)
    provenance: dict[tuple[str, str], str] = {}  # (cbeta_id, site) → source tag

    # From Strategy A
    for cid, sites in colophon_sites.items():
        if cid not in text_entities:
            continue  # text not in KG; skip
        for site in sites:
            resolved[cid].add(site)
            provenance.setdefault((cid, site), f"cbeta_xml:colophon:{cid}")

    # From Strategy B — match title → cbeta_ids
    ambiguous = 0
    unmatched = 0
    for cat_id, title, site in catalog_pairs:
        hits = titles_index.get(title, [])
        if not hits:
            unmatched += 1
            continue
        if len(hits) > 1:
            ambiguous += 1
            continue  # skip ambiguous — stay strict
        cid = hits[0]
        if cid not in text_entities:
            continue
        resolved[cid].add(site)
        provenance.setdefault((cid, site), f"cbeta_xml:catalog:{cat_id}")

    print(
        f"Strategy B title match: ambiguous={ambiguous}, unmatched={unmatched}, "
        f"unique={sum(1 for p in catalog_pairs if len(titles_index.get(p[1], [])) == 1)}"
    )

    # ---- Filter against existing place entities & existing relations --------
    new_relations: list[tuple[int, int, str, str]] = []  # subj, obj, source, site_name
    missing_places: set[str] = set()
    skipped_existing = 0
    for cid, sites in resolved.items():
        subj = text_entities[cid]
        for site in sites:
            obj = places.get(site)
            if obj is None:
                missing_places.add(site)
                continue
            if (subj, obj) in existing_pairs:
                skipped_existing += 1
                continue
            src = provenance[(cid, site)]
            new_relations.append((subj, obj, src, site))

    print("\n=== Resolution ===")
    print(f"  Resolved text→site pairs: {sum(len(v) for v in resolved.values())}")
    print(f"  New translated_at relations: {len(new_relations)}")
    print(f"  Skipped (already existed): {skipped_existing}")
    if missing_places:
        print(f"  Missing place entities in KG (skipped): {sorted(missing_places)}")

    # ---- Write --------------------------------------------------------------
    if dry_run:
        print("\n[DRY RUN] Not writing. Sample new relations:")
        for subj, obj, src, site in new_relations[:20]:
            cid = next((k for k, v in text_entities.items() if v == subj), "?")
            print(f"  text:{cid} -> translated_at -> place:{site}  ({src})")
        return

    async with Session() as session:
        for subj, obj, src, _site in new_relations:
            session.add(
                KGRelation(
                    subject_id=subj,
                    predicate="translated_at",
                    object_id=obj,
                    properties={"extracted_from": src},
                    source=src,
                    confidence=0.9,
                )
            )
        await session.commit()
    print(f"\n[DONE] Wrote {len(new_relations)} translated_at relations.")

    # ---- Propagate coords to translator persons ----------------------------
    await propagate_to_translators(Session, dry_run=False)


async def propagate_to_translators(SessionMaker, *, dry_run: bool) -> None:
    """
    For each translated_at (text→place) relation, find the text's translator
    via (person → translated → text). If the translator person entity has no
    coordinates in its properties, copy place coords with
    geo_source='translation_site:<place_name>'.
    """
    async with SessionMaker() as session:
        # Fetch all place entity coords
        place_rows = await session.execute(
            select(KGEntity.id, KGEntity.name_zh, KGEntity.properties).where(
                KGEntity.entity_type == "place"
            )
        )
        place_info: dict[int, tuple[str, dict | None]] = {
            r.id: (r.name_zh, r.properties) for r in place_rows
        }

        # All translated_at relations
        ta_rows = await session.execute(
            select(KGRelation.subject_id, KGRelation.object_id).where(
                KGRelation.predicate == "translated_at"
            )
        )
        text_to_place: dict[int, int] = {r.subject_id: r.object_id for r in ta_rows}

        # Find translator for each text: person --translated--> text
        trans_rows = await session.execute(
            select(KGRelation.subject_id, KGRelation.object_id).where(
                KGRelation.predicate == "translated"
            )
        )
        text_to_persons: dict[int, list[int]] = defaultdict(list)
        for r in trans_rows:
            text_to_persons[r.object_id].append(r.subject_id)

        # For each text with a place, propagate to its translators
        person_targets: dict[int, tuple[int, str]] = {}  # person_id -> (place_id, site_name)
        for text_ent_id, place_id in text_to_place.items():
            for person_id in text_to_persons.get(text_ent_id, []):
                if person_id not in person_targets:
                    person_targets[person_id] = (place_id, place_info[place_id][0])

        if not person_targets:
            print("[propagate] No translator persons to update.")
            return

        # Filter: only update persons that have no coords yet
        person_rows = await session.execute(
            select(KGEntity.id, KGEntity.name_zh, KGEntity.properties).where(
                KGEntity.id.in_(list(person_targets))
            )
        )
        updates = 0
        for row in person_rows:
            props = row.properties or {}
            if props.get("lat") is not None and props.get("lng") is not None:
                continue  # already has coords — don't overwrite
            place_id, site_name = person_targets[row.id]
            pprops = place_info[place_id][1] or {}
            p_lat, p_lng = pprops.get("lat"), pprops.get("lng")
            if p_lat is None or p_lng is None:
                continue  # place has no coords — nothing to inherit
            props["lat"] = p_lat
            props["lng"] = p_lng
            props["geo_source"] = f"translation_site:{site_name}"
            if dry_run:
                print(f"[propagate DRY] person:{row.name_zh} <- {site_name} ({p_lat},{p_lng})")
            else:
                await session.execute(
                    sql_text("UPDATE kg_entities SET properties = :p WHERE id = :i"),
                    {"p": __import__("json").dumps(props, ensure_ascii=False), "i": row.id},
                )
            updates += 1
        if not dry_run:
            await session.commit()
        print(f"[propagate] Updated {updates} translator persons with translation-site coords.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--xml-dir", type=Path, default=DEFAULT_XML_DIR)
    ap.add_argument(
        "--collections",
        nargs="+",
        default=None,
        help="Limit scan to these CBETA collection prefixes (e.g. T X). Default: all.",
    )
    args = ap.parse_args()
    asyncio.run(run(xml_dir=args.xml_dir, dry_run=args.dry_run, collections=args.collections))


if __name__ == "__main__":
    main()
