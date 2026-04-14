"""Seed hot_questions table from app/data/seed_questions_draft.json.

Idempotent upsert keyed on the slug column (e.g. "q_001"). Safe to run
on every container start — it reconciles display_text / prompt_template
/ category / sort_order for existing rows and deactivates entries that
have been removed from the source file.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.models.hot_question import HotQuestion

VALID_CATEGORIES = {"白话翻译", "经文解读", "对比辨析", "佛教史话"}
SEED_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "seed_questions_draft.json"


def load_seed() -> list[dict]:
    with SEED_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Seed file is not a JSON array: {SEED_PATH}")
    for item in data:
        if item["category"] not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category in {item['id']}: {item['category']}")
    return data


async def upsert(session: AsyncSession, items: list[dict]) -> tuple[int, int, int]:
    existing_rows = (await session.execute(select(HotQuestion))).scalars().all()
    existing = {row.slug: row for row in existing_rows}
    seen_slugs: set[str] = set()
    created = updated = 0

    for idx, item in enumerate(items):
        slug = item["id"]
        seen_slugs.add(slug)
        row = existing.get(slug)
        if row is None:
            session.add(
                HotQuestion(
                    slug=slug,
                    category=item["category"],
                    display_text=item["display_text"],
                    prompt_template=item["prompt_template"],
                    is_active=True,
                    sort_order=idx,
                )
            )
            created += 1
            continue
        changed = False
        if row.category != item["category"]:
            row.category = item["category"]
            changed = True
        if row.display_text != item["display_text"]:
            row.display_text = item["display_text"]
            changed = True
        if row.prompt_template != item["prompt_template"]:
            row.prompt_template = item["prompt_template"]
            changed = True
        if row.sort_order != idx:
            row.sort_order = idx
            changed = True
        if not row.is_active:
            row.is_active = True
            changed = True
        if changed:
            updated += 1

    # Soft-delete rows no longer present in the seed file.
    deactivated = 0
    for slug, row in existing.items():
        if slug not in seen_slugs and row.is_active:
            row.is_active = False
            deactivated += 1

    await session.commit()
    return created, updated, deactivated


async def main() -> None:
    items = load_seed()
    print(f"[seed_hot_questions] Loaded {len(items)} questions from {SEED_PATH}")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as session:
        created, updated, deactivated = await upsert(session, items)
    await engine.dispose()

    print(
        f"[seed_hot_questions] done — created={created} updated={updated} "
        f"deactivated={deactivated}"
    )


if __name__ == "__main__":
    asyncio.run(main())
