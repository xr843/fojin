"""
Import DILA Authority data from GitHub offline repository.

Phase 1: Teacher/student relationships from Person XML (~23,000 relations)
Phase 2: Catalog associations from JSON (contributors, places, dates for ~5,700 texts)

Source: https://github.com/DILA-edu/Authority-Databases (CC BY-SA 3.0)

Usage:
    # Clone data first:
    git clone --depth 1 https://github.com/DILA-edu/Authority-Databases.git /tmp/dila-data

    # Run import:
    python scripts/import_dila_github.py --data-dir /tmp/dila-data
    python scripts/import_dila_github.py --data-dir /tmp/dila-data --phase lineage
    python scripts/import_dila_github.py --data-dir /tmp/dila-data --phase catalog
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lxml import etree
from scripts.base_importer import BaseImporter
from sqlalchemy import select, text

from app.models.knowledge_graph import KGEntity, KGRelation

TEI_NS = "http://www.tei-c.org/ns/1.0"


class DILAGitHubImporter(BaseImporter):
    SOURCE_CODE = "dila"
    SOURCE_NAME_ZH = "DILA 权威数据库"
    SOURCE_NAME_EN = "DILA Authority Database"
    SOURCE_BASE_URL = "https://authority.dila.edu.tw"
    SOURCE_DESCRIPTION = "法鼓文理学院佛学权威数据库（GitHub 离线版），师承关系与经录关联"

    def __init__(self, data_dir: str, phase: str | None = None):
        super().__init__()
        self.data_dir = Path(data_dir)
        self.phase = phase

    async def _get_or_create_entity(
        self, session, *, dila_id: str, name_zh: str, entity_type: str,
        description: str | None = None, properties: dict | None = None,
    ) -> KGEntity | None:
        """Find entity by DILA ID or name, create if not found."""
        if not name_zh:
            return None

        # Try by DILA ID first
        if dila_id:
            result = await session.execute(
                text("SELECT id FROM kg_entities WHERE external_ids->>'dila' = :dila_id"),
                {"dila_id": dila_id},
            )
            row = result.first()
            if row:
                return await session.get(KGEntity, row[0])

        # Try by name
        result = await session.execute(
            select(KGEntity).where(
                KGEntity.entity_type == entity_type,
                KGEntity.name_zh == name_zh,
            )
        )
        entity = result.scalar_one_or_none()

        if entity:
            # Update DILA ID if missing
            if dila_id and (not entity.external_ids or not entity.external_ids.get("dila")):
                ext_ids = dict(entity.external_ids or {})
                ext_ids["dila"] = dila_id
                entity.external_ids = ext_ids
            return entity

        # Create new entity
        entity = KGEntity(
            entity_type=entity_type,
            name_zh=name_zh,
            description=description[:500] if description and len(description) > 500 else description,
            external_ids={"dila": dila_id} if dila_id else None,
            properties=properties,
        )
        session.add(entity)
        await session.flush()
        return entity

    async def _create_relation_if_not_exists(
        self, session, *, subject_id: int, predicate: str, object_id: int, source: str,
    ) -> bool:
        """Create KGRelation if not already exists. Returns True if created."""
        result = await session.execute(
            select(KGRelation).where(
                KGRelation.subject_id == subject_id,
                KGRelation.predicate == predicate,
                KGRelation.object_id == object_id,
            )
        )
        if result.scalar_one_or_none():
            return False

        session.add(KGRelation(
            subject_id=subject_id,
            predicate=predicate,
            object_id=object_id,
            source=source,
            confidence=1.0,
        ))
        return True

    async def import_lineage(self, session):
        """Phase 1: Import teacher/student relationships from Person XML."""
        xml_path = self.data_dir / "authority_person" / "Buddhist_Studies_Person_Authority.xml"
        if not xml_path.exists():
            print(f"  ERROR: {xml_path} not found")
            return

        print(f"  Parsing {xml_path.name} (this may take a moment)...")
        tree = etree.parse(str(xml_path))
        root = tree.getroot()

        persons = root.findall(f".//{{{TEI_NS}}}person")
        print(f"  Found {len(persons)} person elements.")

        # First pass: build a name lookup from XML
        dila_persons: dict[str, dict] = {}  # dila_id -> {name, dynasty, description}
        for person_el in persons:
            dila_id = person_el.get("{http://www.w3.org/XML/1998/namespace}id", "")
            if not dila_id:
                continue

            name_el = person_el.find(f"{{{TEI_NS}}}persName")
            name = name_el.text.strip() if name_el is not None and name_el.text else ""
            if not name:
                continue

            dynasty_el = person_el.find(f".//{{{TEI_NS}}}note[@type='dynasty']")
            dynasty = dynasty_el.text.strip() if dynasty_el is not None and dynasty_el.text else None

            concise_el = person_el.find(f".//{{{TEI_NS}}}note[@type='concise']")
            description = concise_el.text.strip() if concise_el is not None and concise_el.text else None

            dila_persons[dila_id] = {"name": name, "dynasty": dynasty, "description": description}

        print(f"  Built name lookup for {len(dila_persons)} persons.")

        # Second pass: extract relations
        relations_created = 0
        batch_count = 0

        for person_el in persons:
            dila_id = person_el.get("{http://www.w3.org/XML/1998/namespace}id", "")
            if not dila_id or dila_id not in dila_persons:
                continue

            list_rel = person_el.find(f"{{{TEI_NS}}}listRelation")
            if list_rel is None:
                continue

            person_info = dila_persons[dila_id]
            current_entity = await self._get_or_create_entity(
                session,
                dila_id=dila_id,
                name_zh=person_info["name"],
                entity_type="person",
                description=person_info.get("description"),
                properties={"dynasty": person_info["dynasty"]} if person_info.get("dynasty") else None,
            )
            if not current_entity:
                continue

            for relation_el in list_rel.findall(f"{{{TEI_NS}}}relation"):
                rel_type = relation_el.get("type", "")
                active_id = relation_el.get("active", "")
                active_name = relation_el.get("n", "")

                if rel_type not in ("teacher", "student") or not active_id:
                    continue

                # Get or create the other entity
                other_info = dila_persons.get(active_id, {})
                other_name = other_info.get("name") or active_name
                if not other_name:
                    continue

                other_entity = await self._get_or_create_entity(
                    session,
                    dila_id=active_id,
                    name_zh=other_name,
                    entity_type="person",
                    description=other_info.get("description"),
                    properties={"dynasty": other_info["dynasty"]} if other_info.get("dynasty") else None,
                )
                if not other_entity:
                    continue

                # Create relation: teacher_of goes from teacher to student
                if rel_type == "teacher":
                    created = await self._create_relation_if_not_exists(
                        session,
                        subject_id=other_entity.id,  # teacher
                        predicate="teacher_of",
                        object_id=current_entity.id,  # student
                        source="dila",
                    )
                else:  # student
                    created = await self._create_relation_if_not_exists(
                        session,
                        subject_id=current_entity.id,  # teacher
                        predicate="teacher_of",
                        object_id=other_entity.id,  # student
                        source="dila",
                    )

                if created:
                    relations_created += 1

            batch_count += 1
            if batch_count % 500 == 0:
                await session.flush()
                print(f"    Processed {batch_count} persons, {relations_created} relations created...")

        await session.flush()
        self.stats.relations_created += relations_created
        print(f"  Lineage import done: {relations_created} teacher/student relations created.")

    async def import_catalog(self, session):
        """Phase 2: Import catalog associations (contributors, places)."""
        json_dir = self.data_dir / "authority_catalog" / "json"
        if not json_dir.exists():
            print(f"  ERROR: {json_dir} not found")
            return

        json_files = sorted(json_dir.glob("*.json"))
        print(f"  Found {len(json_files)} catalog JSON files.")

        relations_created = 0
        texts_updated = 0

        for json_path in json_files:
            canon_code = json_path.stem  # e.g. "T", "X"
            with open(json_path, encoding="utf-8") as f:
                entries = json.load(f)

            if not isinstance(entries, list):
                continue

            for entry in entries:
                vol = entry.get("vol", "")
                title = entry.get("title", "")
                if not vol or not title:
                    continue

                # Match to buddhist_texts by cbeta_id pattern (e.g. "T0001")
                # vol format: "T01" -> cbeta_id starts with "T"
                # Extract text number from authorityID: CA0000001 -> not useful
                # Better: match by canon + title
                cbeta_prefix = canon_code  # T, X, etc.

                # Try to find matching text by title + source canon
                result = await session.execute(
                    text("""
                        SELECT id FROM buddhist_texts
                        WHERE cbeta_id LIKE :prefix AND title_zh = :title
                        LIMIT 1
                    """),
                    {"prefix": f"{cbeta_prefix}%", "title": title},
                )
                text_row = result.first()

                # Import contributors as person entities + relations
                contributors = entry.get("contributors", [])
                for contrib in contributors:
                    c_name = contrib.get("name", "")
                    c_id = contrib.get("id", "")
                    if not c_name:
                        continue

                    person = await self._get_or_create_entity(
                        session,
                        dila_id=c_id,
                        name_zh=c_name,
                        entity_type="person",
                        properties={"dynasty": entry.get("dynasty")} if entry.get("dynasty") else None,
                    )
                    if not person or not text_row:
                        continue

                    # Find or create KGEntity for the text
                    text_entity_result = await session.execute(
                        select(KGEntity).where(
                            KGEntity.entity_type == "text",
                            KGEntity.text_id == text_row[0],
                        )
                    )
                    text_entity = text_entity_result.scalar_one_or_none()
                    if not text_entity:
                        continue

                    created = await self._create_relation_if_not_exists(
                        session,
                        subject_id=person.id,
                        predicate="translated",
                        object_id=text_entity.id,
                        source="dila_catalog",
                    )
                    if created:
                        relations_created += 1

                # Import places
                places = entry.get("places", [])
                for place in places:
                    p_name = place.get("name", "")
                    p_id = place.get("id", "")
                    if not p_name:
                        continue

                    props = {}
                    if place.get("lat") and place.get("long"):
                        props["latitude"] = float(place["lat"])
                        props["longitude"] = float(place["long"])

                    place_entity = await self._get_or_create_entity(
                        session,
                        dila_id=p_id,
                        name_zh=p_name,
                        entity_type="place",
                        properties=props if props else None,
                    )
                    if not place_entity:
                        continue

                    # Link contributors to places (active_in)
                    for contrib in contributors:
                        c_name = contrib.get("name", "")
                        c_id = contrib.get("id", "")
                        if not c_name:
                            continue

                        person = await self._get_or_create_entity(
                            session,
                            dila_id=c_id,
                            name_zh=c_name,
                            entity_type="person",
                        )
                        if person:
                            created = await self._create_relation_if_not_exists(
                                session,
                                subject_id=person.id,
                                predicate="active_in",
                                object_id=place_entity.id,
                                source="dila_catalog",
                            )
                            if created:
                                relations_created += 1

            await session.flush()
            print(f"    {canon_code}: processed {len(entries)} entries")

        self.stats.relations_created += relations_created
        self.stats.texts_updated += texts_updated
        print(f"  Catalog import done: {relations_created} relations created.")

    async def run_import(self):
        if not self.data_dir.exists():
            raise FileNotFoundError(
                f"Data directory not found: {self.data_dir}\n"
                "Clone it first: git clone --depth 1 "
                "https://github.com/DILA-edu/Authority-Databases.git /tmp/dila-data"
            )

        async with self.session_factory() as session:
            await self.ensure_source(session)

            if self.phase in (None, "lineage"):
                await self.import_lineage(session)

            if self.phase in (None, "catalog"):
                await self.import_catalog(session)

            await session.commit()


async def main():
    parser = argparse.ArgumentParser(description="Import DILA Authority data from GitHub repo")
    parser.add_argument("--data-dir", required=True, help="Path to cloned DILA Authority-Databases repo")
    parser.add_argument("--phase", choices=["lineage", "catalog"], help="Import only specific phase")
    args = parser.parse_args()

    importer = DILAGitHubImporter(data_dir=args.data_dir, phase=args.phase)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
