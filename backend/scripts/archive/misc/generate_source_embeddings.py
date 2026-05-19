"""Generate embeddings for data sources and store in data_sources.embedding.

Usage:
    docker compose exec -T backend python scripts/generate_source_embeddings.py
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.database import engine as async_engine
from app.services.embedding import generate_embeddings_batch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

LANGUAGE_NAMES = {
    "zh": "中文", "lzh": "古汉语", "pi": "巴利语", "sa": "梵文", "bo": "藏文",
    "en": "英文", "ja": "日文", "ko": "韩文", "vi": "越南文", "th": "泰文",
    "my": "缅甸文", "km": "高棉文", "mn": "蒙古文", "de": "德文", "fr": "法文",
    "si": "僧伽罗文", "lo": "老挝文", "id": "印尼文",
}

FIELD_NAMES = {
    "han": "汉传佛教", "theravada": "南传佛教", "tibetan": "藏传佛教",
    "sanskrit": "梵文佛典", "dunhuang": "敦煌学", "art": "佛教艺术",
    "dictionary": "辞典工具", "dh": "数字人文",
}

BATCH_SIZE = 20


def build_source_text(row: dict) -> str:
    """Build structured text for embedding from a data source row."""
    parts = [f"数据源：{row['name_zh']}"]
    if row.get("name_en"):
        parts[0] += f"（{row['name_en']}）"

    if row.get("description"):
        parts.append(f"简介：{row['description']}")

    if row.get("languages"):
        lang_names = [LANGUAGE_NAMES.get(c.strip(), c.strip()) for c in row["languages"].split(",") if c.strip()]
        if lang_names:
            parts.append(f"语种：{'、'.join(lang_names)}")

    if row.get("research_fields"):
        field_names = [FIELD_NAMES.get(f.strip(), f.strip()) for f in row["research_fields"].split(",") if f.strip()]
        if field_names:
            parts.append(f"研究领域：{'、'.join(field_names)}")

    if row.get("region"):
        parts.append(f"地区：{row['region']}")

    return "\n".join(parts)


async def main() -> None:
    async with async_engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT id, code, name_zh, name_en, description, languages, "
            "research_fields, region FROM data_sources WHERE is_active = true"
        ))
        sources = [dict(r._mapping) for r in result.fetchall()]

    logger.info("Found %d active data sources", len(sources))

    # Build texts
    source_texts = [(s["id"], build_source_text(s)) for s in sources]
    updated = 0

    # Process in batches
    for i in range(0, len(source_texts), BATCH_SIZE):
        batch = source_texts[i:i + BATCH_SIZE]
        ids = [s[0] for s in batch]
        texts = [s[1] for s in batch]

        logger.info("Generating embeddings for batch %d/%d (%d sources)...",
                     i // BATCH_SIZE + 1, (len(source_texts) + BATCH_SIZE - 1) // BATCH_SIZE, len(batch))

        embeddings = await generate_embeddings_batch(texts)

        # Write back to DB using raw driver SQL ($1/$2 placeholders for asyncpg)
        async with async_engine.connect() as conn:
            raw_conn = await conn.get_raw_connection()
            for source_id, embedding in zip(ids, embeddings, strict=True):
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                await raw_conn.driver_connection.execute(
                    "UPDATE data_sources SET embedding = $1::vector WHERE id = $2",
                    embedding_str, source_id,
                )
                updated += 1

    logger.info("Done. Updated %d / %d sources with embeddings.", updated, len(sources))


if __name__ == "__main__":
    asyncio.run(main())
