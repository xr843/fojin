# Timeline & Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a multi-dimensional historical timeline (`/timeline`) and a data statistics dashboard (`/dashboard`) to FoJin, using existing data without model changes.

**Architecture:** Two new read-only pages sharing a dynasty-year mapping config and a new `/api/stats/` router. Backend aggregates existing `buddhist_texts`, `kg_entities`, `kg_relations`, and `data_sources` tables into cached endpoints. Frontend renders with D3.js (already installed) and Ant Design grid.

**Tech Stack:** FastAPI + SQLAlchemy async + Redis cache (backend), React 18 + D3.js + Ant Design 5 + TanStack Query + Zustand (frontend)

---

## File Structure

```
backend/
  app/core/dynasty_config.py        # CREATE — Dynasty-year mapping (Python dict)
  app/services/stats_service.py     # CREATE — Aggregation queries
  app/api/stats.py                  # CREATE — /api/stats/overview + /api/stats/timeline
  app/main.py                       # MODIFY — Register stats router (line ~138)
  tests/test_stats.py               # CREATE — Tests for stats endpoints

frontend/
  src/data/dynasty_years.ts         # CREATE — Dynasty-year mapping (must match backend)
  src/api/stats.ts                  # CREATE — API client for stats endpoints
  src/stores/timelineStore.ts       # CREATE — Zustand store for timeline filters + scholarly mode
  src/pages/DashboardPage.tsx       # CREATE — Dashboard page
  src/pages/TimelinePage.tsx        # CREATE — Timeline page
  src/components/dashboard/
    SummaryCards.tsx                 # CREATE — Platform summary number cards
    DynastyBarChart.tsx             # CREATE — Dynasty distribution bar chart
    LanguageDonut.tsx               # CREATE — Language distribution donut
    CategoryTreemap.tsx             # CREATE — Category breakdown treemap
    SourceCoverageChart.tsx         # CREATE — Data source coverage stacked bar
    TranslationTrendChart.tsx       # CREATE — Translation activity area chart
    TopTranslatorsChart.tsx         # CREATE — Top translators bar chart
  src/components/timeline/
    TimelineChart.tsx               # CREATE — Main D3 timeline with zoom/pan
    DynastyBands.tsx                # CREATE — Background dynasty color strips
    TimelineFilters.tsx             # CREATE — Filter sidebar
    TimelineTooltip.tsx             # CREATE — Hover tooltip
  src/styles/dashboard.css          # CREATE — Dashboard styles
  src/styles/timeline.css           # CREATE — Timeline styles
  src/components/Layout.tsx         # MODIFY — Add nav items (line ~60)
  src/App.tsx                       # MODIFY — Add lazy routes (line ~33)
  public/locales/zh/translation.json # MODIFY — Add i18n keys
  public/locales/en/translation.json # MODIFY — Add i18n keys
```

---

### Task 1: Dynasty Config (Backend)

**Files:**
- Create: `backend/app/core/dynasty_config.py`

- [ ] **Step 1: Write the dynasty config module**

```python
# backend/app/core/dynasty_config.py
"""Dynasty-to-year mapping shared across stats endpoints.

Keep in sync with frontend/src/data/dynasty_years.ts.
"""

DYNASTIES: list[dict] = [
    {"key": "pre_qin", "name_zh": "先秦", "name_en": "Pre-Qin", "start": -770, "end": -221},
    {"key": "qin", "name_zh": "秦", "name_en": "Qin Dynasty", "start": -221, "end": -206},
    {"key": "western_han", "name_zh": "西汉", "name_en": "Western Han", "start": -206, "end": 8},
    {"key": "eastern_han", "name_zh": "東漢", "name_en": "Eastern Han", "start": 25, "end": 220},
    {"key": "three_kingdoms", "name_zh": "三國", "name_en": "Three Kingdoms", "start": 220, "end": 280},
    {"key": "western_jin", "name_zh": "西晉", "name_en": "Western Jin", "start": 265, "end": 316},
    {"key": "eastern_jin", "name_zh": "東晉", "name_en": "Eastern Jin", "start": 317, "end": 420},
    {"key": "sixteen_kingdoms", "name_zh": "十六國", "name_en": "Sixteen Kingdoms", "start": 304, "end": 439},
    {"key": "southern_dynasties", "name_zh": "南朝", "name_en": "Southern Dynasties", "start": 420, "end": 589},
    {"key": "northern_dynasties", "name_zh": "北朝", "name_en": "Northern Dynasties", "start": 386, "end": 581},
    {"key": "sui", "name_zh": "隋", "name_en": "Sui Dynasty", "start": 581, "end": 618},
    {"key": "tang", "name_zh": "唐", "name_en": "Tang Dynasty", "start": 618, "end": 907},
    {"key": "five_dynasties", "name_zh": "五代", "name_en": "Five Dynasties", "start": 907, "end": 960},
    {"key": "northern_song", "name_zh": "北宋", "name_en": "Northern Song", "start": 960, "end": 1127},
    {"key": "southern_song", "name_zh": "南宋", "name_en": "Southern Song", "start": 1127, "end": 1279},
    {"key": "liao", "name_zh": "遼", "name_en": "Liao Dynasty", "start": 916, "end": 1125},
    {"key": "jin_jurchen", "name_zh": "金", "name_en": "Jin (Jurchen)", "start": 1115, "end": 1234},
    {"key": "yuan", "name_zh": "元", "name_en": "Yuan Dynasty", "start": 1271, "end": 1368},
    {"key": "ming", "name_zh": "明", "name_en": "Ming Dynasty", "start": 1368, "end": 1644},
    {"key": "qing", "name_zh": "清", "name_en": "Qing Dynasty", "start": 1644, "end": 1912},
    {"key": "modern", "name_zh": "近現代", "name_en": "Modern", "start": 1912, "end": 2000},
    {"key": "india", "name_zh": "印度", "name_en": "India", "start": -500, "end": 1200},
    {"key": "japan", "name_zh": "日本", "name_en": "Japan", "start": 600, "end": 1900},
    {"key": "korea", "name_zh": "高麗/朝鮮", "name_en": "Korea", "start": 918, "end": 1910},
    {"key": "tibet", "name_zh": "西藏", "name_en": "Tibet", "start": 600, "end": 1900},
]

# Lookup: name_zh -> dynasty dict
_BY_NAME: dict[str, dict] = {}
for d in DYNASTIES:
    _BY_NAME[d["name_zh"]] = d


# Common aliases from TRANSLATOR_DYNASTIES in scripts_shared.py
_ALIASES: dict[str, str] = {
    "後漢": "東漢",
    "劉宋": "南朝",
    "蕭齊": "南朝",
    "蕭梁": "南朝",
    "曹魏": "三國",
    "吳": "三國",
    "東吳": "三國",
    "北涼": "十六國",
    "後秦": "十六國",
    "姚秦": "十六國",
    "前秦": "十六國",
    "西秦": "十六國",
    "北魏": "北朝",
    "東魏": "北朝",
    "西魏": "北朝",
    "北齊": "北朝",
    "北周": "北朝",
    "宋": "北宋",
    "南齊": "南朝",
    "梁": "南朝",
    "陳": "南朝",
}


def resolve_dynasty(name_zh: str | None) -> dict | None:
    """Resolve a dynasty name (including aliases) to its config entry."""
    if not name_zh:
        return None
    canonical = _ALIASES.get(name_zh, name_zh)
    return _BY_NAME.get(canonical)


def get_year_range(name_zh: str | None) -> tuple[int, int] | None:
    """Return (start, end) year tuple for a dynasty name, or None."""
    d = resolve_dynasty(name_zh)
    if d:
        return (d["start"], d["end"])
    return None
```

- [ ] **Step 2: Verify linting passes**

Run: `cd ~/projects/fojin/backend && ruff check app/core/dynasty_config.py`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/dynasty_config.py
git commit -m "feat(stats): add dynasty-year mapping config"
```

---

### Task 2: Stats Service (Backend)

**Files:**
- Create: `backend/app/services/stats_service.py`

- [ ] **Step 1: Write the failing test for overview endpoint**

Create `backend/tests/test_stats.py`:

```python
"""Tests for stats API endpoints."""

import pytest

from app.core.dynasty_config import resolve_dynasty, get_year_range


def test_resolve_dynasty_direct():
    d = resolve_dynasty("唐")
    assert d is not None
    assert d["key"] == "tang"
    assert d["start"] == 618


def test_resolve_dynasty_alias():
    d = resolve_dynasty("姚秦")
    assert d is not None
    assert d["name_zh"] == "十六國"


def test_resolve_dynasty_none():
    assert resolve_dynasty(None) is None
    assert resolve_dynasty("不存在") is None


def test_get_year_range():
    r = get_year_range("唐")
    assert r == (618, 907)


def test_get_year_range_none():
    assert get_year_range("不存在") is None


@pytest.mark.asyncio
async def test_stats_overview(client):
    resp = await client.get("/api/stats/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert "dynasty_distribution" in data
    assert "language_distribution" in data
    assert "category_distribution" in data
    assert "top_translators" in data


@pytest.mark.asyncio
async def test_stats_timeline_texts(client):
    resp = await client.get("/api/stats/timeline", params={"dimension": "texts"})
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_stats_timeline_invalid_dimension(client):
    resp = await client.get("/api/stats/timeline", params={"dimension": "invalid"})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/projects/fojin/backend && python -m pytest tests/test_stats.py -v`
Expected: dynasty config tests PASS, API tests FAIL (no endpoint yet)

- [ ] **Step 3: Write the stats service**

Create `backend/app/services/stats_service.py`:

```python
"""Aggregation queries for stats endpoints."""

import hashlib
import json
import logging

from sqlalchemy import String, case, func, literal_column, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dynasty_config import DYNASTIES, resolve_dynasty
from app.models.dictionary import DictionaryEntry
from app.models.knowledge_graph import KGEntity, KGRelation
from app.models.source import DataSource
from app.models.text import BuddhistText

logger = logging.getLogger(__name__)


async def get_overview(db: AsyncSession, redis) -> dict:
    """Return aggregated platform statistics. Cached in Redis for 1 hour."""
    cache_key = "stats:overview"
    if redis:
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

    # Summary counts
    total_texts = (await db.execute(select(func.count(BuddhistText.id)))).scalar() or 0
    total_sources = (await db.execute(select(func.count(DataSource.id)).where(DataSource.is_active == True))).scalar() or 0
    total_kg_entities = (await db.execute(select(func.count(KGEntity.id)))).scalar() or 0
    total_kg_relations = (await db.execute(select(func.count(KGRelation.id)))).scalar() or 0
    total_dict_entries = (await db.execute(select(func.count(DictionaryEntry.id)))).scalar() or 0

    # Distinct languages from texts (lang column)
    lang_q = select(BuddhistText.lang, func.count(BuddhistText.id)).where(
        BuddhistText.lang.is_not(None)
    ).group_by(BuddhistText.lang).order_by(func.count(BuddhistText.id).desc())
    lang_rows = (await db.execute(lang_q)).all()
    total_languages = len(lang_rows)

    # Dynasty distribution
    dynasty_q = select(BuddhistText.dynasty, func.count(BuddhistText.id)).where(
        BuddhistText.dynasty.is_not(None)
    ).group_by(BuddhistText.dynasty).order_by(func.count(BuddhistText.id).desc())
    dynasty_rows = (await db.execute(dynasty_q)).all()
    dynasty_distribution = []
    for dynasty_name, count in dynasty_rows:
        d = resolve_dynasty(dynasty_name)
        dynasty_distribution.append({
            "dynasty": dynasty_name,
            "count": count,
            "year_start": d["start"] if d else None,
            "year_end": d["end"] if d else None,
        })

    # Category distribution
    cat_q = select(BuddhistText.category, func.count(BuddhistText.id)).where(
        BuddhistText.category.is_not(None)
    ).group_by(BuddhistText.category).order_by(func.count(BuddhistText.id).desc())
    cat_rows = (await db.execute(cat_q)).all()
    category_distribution = [{"category": c, "count": n} for c, n in cat_rows]

    # Source coverage: per source — texts with content vs without
    src_q = select(
        DataSource.name_zh,
        func.count(BuddhistText.id),
        func.sum(case((BuddhistText.has_content == True, 1), else_=0)),
    ).join(BuddhistText, BuddhistText.source_id == DataSource.id).group_by(
        DataSource.name_zh
    ).order_by(func.count(BuddhistText.id).desc())
    src_rows = (await db.execute(src_q)).all()
    source_coverage = []
    for name, total, with_content in src_rows:
        with_content = with_content or 0
        source_coverage.append({
            "source_name": name,
            "full_content": with_content,
            "metadata_only": total - with_content,
        })

    # Top translators
    trans_q = select(
        BuddhistText.translator,
        BuddhistText.dynasty,
        func.count(BuddhistText.id),
    ).where(
        BuddhistText.translator.is_not(None),
        BuddhistText.translator != "",
    ).group_by(
        BuddhistText.translator, BuddhistText.dynasty
    ).order_by(func.count(BuddhistText.id).desc()).limit(15)
    trans_rows = (await db.execute(trans_q)).all()
    top_translators = [{"name": n, "dynasty": d, "count": c} for n, d, c in trans_rows]

    result = {
        "summary": {
            "total_texts": total_texts,
            "total_sources": total_sources,
            "total_languages": total_languages,
            "total_kg_entities": total_kg_entities,
            "total_kg_relations": total_kg_relations,
            "total_dict_entries": total_dict_entries,
        },
        "dynasty_distribution": dynasty_distribution,
        "language_distribution": [{"language": l, "count": c} for l, c in lang_rows],
        "category_distribution": category_distribution,
        "source_coverage": source_coverage,
        "top_translators": top_translators,
    }

    if redis:
        await redis.set(cache_key, json.dumps(result, ensure_ascii=False), ex=3600)

    return result


async def get_timeline(
    db: AsyncSession,
    redis,
    dimension: str,
    category: str | None = None,
    language: str | None = None,
    source_id: str | None = None,
    page: int = 1,
    page_size: int = 200,
) -> dict:
    """Return timeline items for a given dimension. Cached for 1 hour."""
    # Build cache key from params
    params_str = f"{dimension}:{category}:{language}:{source_id}:{page}:{page_size}"
    cache_key = f"stats:timeline:{hashlib.md5(params_str.encode()).hexdigest()}"
    if redis:
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

    offset = (page - 1) * page_size

    if dimension == "texts":
        result = await _timeline_texts(db, category, language, source_id, offset, page_size)
    elif dimension == "figures":
        result = await _timeline_figures(db, offset, page_size)
    elif dimension == "schools":
        result = await _timeline_schools(db, offset, page_size)
    else:
        raise ValueError(f"Invalid dimension: {dimension}")

    if redis:
        await redis.set(cache_key, json.dumps(result, ensure_ascii=False), ex=3600)

    return result


async def _timeline_texts(db, category, language, source_id, offset, page_size) -> dict:
    q = select(
        BuddhistText.id,
        BuddhistText.title_zh,
        BuddhistText.title_en,
        BuddhistText.dynasty,
        BuddhistText.translator,
        BuddhistText.category,
        BuddhistText.lang,
    ).where(BuddhistText.dynasty.is_not(None))

    count_q = select(func.count(BuddhistText.id)).where(BuddhistText.dynasty.is_not(None))

    if category:
        cats = [c.strip() for c in category.split(",")]
        q = q.where(BuddhistText.category.in_(cats))
        count_q = count_q.where(BuddhistText.category.in_(cats))
    if language:
        langs = [l.strip() for l in language.split(",")]
        q = q.where(BuddhistText.lang.in_(langs))
        count_q = count_q.where(BuddhistText.lang.in_(langs))
    if source_id:
        sids = [int(s.strip()) for s in source_id.split(",")]
        q = q.where(BuddhistText.source_id.in_(sids))
        count_q = count_q.where(BuddhistText.source_id.in_(sids))

    total = (await db.execute(count_q)).scalar() or 0

    q = q.order_by(BuddhistText.dynasty, BuddhistText.id).offset(offset).limit(page_size)
    rows = (await db.execute(q)).all()

    items = []
    for r in rows:
        d = resolve_dynasty(r.dynasty)
        items.append({
            "id": r.id,
            "name_zh": r.title_zh,
            "name_en": r.title_en,
            "dynasty": r.dynasty,
            "year_start": d["start"] if d else None,
            "year_end": d["end"] if d else None,
            "category": r.category,
            "translator": r.translator,
        })

    return {"items": items, "total": total}


async def _timeline_figures(db, offset, page_size) -> dict:
    q = select(
        KGEntity.id,
        KGEntity.name_zh,
        KGEntity.name_en,
        KGEntity.properties,
    ).where(
        KGEntity.entity_type == "person"
    ).order_by(KGEntity.id).offset(offset).limit(page_size)

    count_q = select(func.count(KGEntity.id)).where(KGEntity.entity_type == "person")
    total = (await db.execute(count_q)).scalar() or 0
    rows = (await db.execute(q)).all()

    items = []
    for r in rows:
        props = r.properties or {}
        dynasty_name = props.get("dynasty")
        d = resolve_dynasty(dynasty_name)
        items.append({
            "id": r.id,
            "name_zh": r.name_zh,
            "name_en": r.name_en,
            "dynasty": dynasty_name,
            "year_start": d["start"] if d else None,
            "year_end": d["end"] if d else None,
            "entity_type": "person",
        })

    return {"items": items, "total": total}


async def _timeline_schools(db, offset, page_size) -> dict:
    q = select(
        KGEntity.id,
        KGEntity.name_zh,
        KGEntity.name_en,
        KGEntity.properties,
    ).where(
        KGEntity.entity_type == "school"
    ).order_by(KGEntity.id).offset(offset).limit(page_size)

    count_q = select(func.count(KGEntity.id)).where(KGEntity.entity_type == "school")
    total = (await db.execute(count_q)).scalar() or 0
    rows = (await db.execute(q)).all()

    items = []
    for r in rows:
        props = r.properties or {}
        dynasty_name = props.get("dynasty") or props.get("period")
        d = resolve_dynasty(dynasty_name)
        items.append({
            "id": r.id,
            "name_zh": r.name_zh,
            "name_en": r.name_en,
            "dynasty": dynasty_name,
            "year_start": d["start"] if d else None,
            "year_end": d["end"] if d else None,
            "entity_type": "school",
        })

    return {"items": items, "total": total}
```

- [ ] **Step 4: Verify linting passes**

Run: `cd ~/projects/fojin/backend && ruff check app/services/stats_service.py`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/stats_service.py
git commit -m "feat(stats): add stats aggregation service"
```

---

### Task 3: Stats Router + Registration (Backend)

**Files:**
- Create: `backend/app/api/stats.py`
- Modify: `backend/app/main.py:24-45` (imports) and `~138` (router registration)

- [ ] **Step 1: Write the stats router**

Create `backend/app/api/stats.py`:

```python
"""Stats API endpoints for timeline and dashboard."""

from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.stats_service import get_overview, get_timeline

router = APIRouter(prefix="/stats", tags=["stats"])


class TimelineDimension(str, Enum):
    texts = "texts"
    figures = "figures"
    schools = "schools"


@router.get("/overview")
async def stats_overview(db: AsyncSession = Depends(get_db)):
    """Return aggregated platform statistics for the dashboard."""
    from app.main import app
    redis = getattr(app.state, "redis", None)
    return await get_overview(db, redis)


@router.get("/timeline")
async def stats_timeline(
    dimension: TimelineDimension = Query(..., description="Timeline dimension"),
    category: str | None = Query(None, description="Filter by category (comma-separated)"),
    language: str | None = Query(None, description="Filter by language (comma-separated)"),
    source_id: str | None = Query(None, description="Filter by source ID (comma-separated)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(200, ge=1, le=500, description="Items per page"),
    db: AsyncSession = Depends(get_db),
):
    """Return timeline items for visualization."""
    from app.main import app
    redis = getattr(app.state, "redis", None)
    return await get_timeline(db, redis, dimension.value, category, language, source_id, page, page_size)
```

- [ ] **Step 2: Register the router in main.py**

In `backend/app/main.py`, add to the imports (around line 24):
```python
from app.api import (
    annotations,
    auth,
    bookmarks,
    chat,
    citations,
    dictionary,
    exports,
    history,
    iiif,
    knowledge_graph,
    relations,
    search,
    source_suggestions,
    sources,
    stats,          # <-- ADD THIS LINE
    texts,
)
```

Then add after the Phase 4 routers block (around line 138):
```python
# Stats (timeline + dashboard)
app.include_router(stats.router, prefix="/api")
```

- [ ] **Step 3: Run all tests**

Run: `cd ~/projects/fojin/backend && python -m pytest tests/test_stats.py -v`
Expected: ALL PASS

- [ ] **Step 4: Run full backend lint + test**

Run: `cd ~/projects/fojin/backend && ruff check app/ && python -m pytest tests/ -q`
Expected: no lint errors, all tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/stats.py backend/app/main.py backend/tests/test_stats.py
git commit -m "feat(stats): add stats API router with overview and timeline endpoints"
```

---

### Task 4: Dynasty Config (Frontend)

**Files:**
- Create: `frontend/src/data/dynasty_years.ts`

- [ ] **Step 1: Write the dynasty config**

Create `frontend/src/data/dynasty_years.ts` — must match `backend/app/core/dynasty_config.py` exactly:

```typescript
export interface DynastyPeriod {
  key: string;
  name_zh: string;
  name_en: string;
  start: number;
  end: number;
  color: string;
}

export const DYNASTIES: DynastyPeriod[] = [
  { key: "pre_qin", name_zh: "先秦", name_en: "Pre-Qin", start: -770, end: -221, color: "#8b7355" },
  { key: "qin", name_zh: "秦", name_en: "Qin Dynasty", start: -221, end: -206, color: "#4a4a4a" },
  { key: "western_han", name_zh: "西汉", name_en: "Western Han", start: -206, end: 8, color: "#c75450" },
  { key: "eastern_han", name_zh: "東漢", name_en: "Eastern Han", start: 25, end: 220, color: "#d4756b" },
  { key: "three_kingdoms", name_zh: "三國", name_en: "Three Kingdoms", start: 220, end: 280, color: "#6b8e5b" },
  { key: "western_jin", name_zh: "西晉", name_en: "Western Jin", start: 265, end: 316, color: "#7a9e6a" },
  { key: "eastern_jin", name_zh: "東晉", name_en: "Eastern Jin", start: 317, end: 420, color: "#8aae7a" },
  { key: "sixteen_kingdoms", name_zh: "十六國", name_en: "Sixteen Kingdoms", start: 304, end: 439, color: "#9b8b6e" },
  { key: "southern_dynasties", name_zh: "南朝", name_en: "Southern Dynasties", start: 420, end: 589, color: "#b08d57" },
  { key: "northern_dynasties", name_zh: "北朝", name_en: "Northern Dynasties", start: 386, end: 581, color: "#a07d47" },
  { key: "sui", name_zh: "隋", name_en: "Sui Dynasty", start: 581, end: 618, color: "#4a7c9b" },
  { key: "tang", name_zh: "唐", name_en: "Tang Dynasty", start: 618, end: 907, color: "#c75450" },
  { key: "five_dynasties", name_zh: "五代", name_en: "Five Dynasties", start: 907, end: 960, color: "#8b6e5b" },
  { key: "northern_song", name_zh: "北宋", name_en: "Northern Song", start: 960, end: 1127, color: "#4a7c9b" },
  { key: "southern_song", name_zh: "南宋", name_en: "Southern Song", start: 1127, end: 1279, color: "#5a8cab" },
  { key: "liao", name_zh: "遼", name_en: "Liao Dynasty", start: 916, end: 1125, color: "#7a6e5b" },
  { key: "jin_jurchen", name_zh: "金", name_en: "Jin (Jurchen)", start: 1115, end: 1234, color: "#b08d57" },
  { key: "yuan", name_zh: "元", name_en: "Yuan Dynasty", start: 1271, end: 1368, color: "#4a6a4a" },
  { key: "ming", name_zh: "明", name_en: "Ming Dynasty", start: 1368, end: 1644, color: "#8b2500" },
  { key: "qing", name_zh: "清", name_en: "Qing Dynasty", start: 1644, end: 1912, color: "#b08d57" },
  { key: "modern", name_zh: "近現代", name_en: "Modern", start: 1912, end: 2000, color: "#4a4a4a" },
  { key: "india", name_zh: "印度", name_en: "India", start: -500, end: 1200, color: "#d4a56a" },
  { key: "japan", name_zh: "日本", name_en: "Japan", start: 600, end: 1900, color: "#c75480" },
  { key: "korea", name_zh: "高麗/朝鮮", name_en: "Korea", start: 918, end: 1910, color: "#5470c6" },
  { key: "tibet", name_zh: "西藏", name_en: "Tibet", start: 600, end: 1900, color: "#91cc75" },
];

const ALIASES: Record<string, string> = {
  "後漢": "東漢", "劉宋": "南朝", "蕭齊": "南朝", "蕭梁": "南朝",
  "曹魏": "三國", "吳": "三國", "東吳": "三國",
  "北涼": "十六國", "後秦": "十六國", "姚秦": "十六國", "前秦": "十六國", "西秦": "十六國",
  "北魏": "北朝", "東魏": "北朝", "西魏": "北朝", "北齊": "北朝", "北周": "北朝",
  "宋": "北宋", "南齊": "南朝", "梁": "南朝", "陳": "南朝",
};

const BY_NAME = new Map(DYNASTIES.map((d) => [d.name_zh, d]));

export function resolveDynasty(nameZh: string | null | undefined): DynastyPeriod | undefined {
  if (!nameZh) return undefined;
  const canonical = ALIASES[nameZh] ?? nameZh;
  return BY_NAME.get(canonical);
}
```

- [ ] **Step 2: Verify lint passes**

Run: `cd ~/projects/fojin/frontend && npx eslint src/data/dynasty_years.ts`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/data/dynasty_years.ts
git commit -m "feat(stats): add dynasty-year mapping config (frontend)"
```

---

### Task 5: Stats API Client + Store (Frontend)

**Files:**
- Create: `frontend/src/api/stats.ts`
- Create: `frontend/src/stores/timelineStore.ts`

- [ ] **Step 1: Write the API client**

Create `frontend/src/api/stats.ts`:

```typescript
import axios from "axios";

// Reuse the shared axios instance from client.ts
// Import it by creating a thin wrapper using the same base config
const api = axios.create({
  baseURL: "/api",
  timeout: 15000,
});

// Attach JWT same as client.ts
api.interceptors.request.use((config) => {
  try {
    const raw = localStorage.getItem("fojin-auth");
    if (raw) {
      const { state } = JSON.parse(raw);
      if (state?.token) {
        config.headers.Authorization = `Bearer ${state.token}`;
      }
    }
  } catch {
    // ignore
  }
  return config;
});

export interface StatsSummary {
  total_texts: number;
  total_sources: number;
  total_languages: number;
  total_kg_entities: number;
  total_kg_relations: number;
  total_dict_entries: number;
}

export interface DynastyDistribution {
  dynasty: string;
  count: number;
  year_start: number | null;
  year_end: number | null;
}

export interface LanguageDistribution {
  language: string;
  count: number;
}

export interface CategoryDistribution {
  category: string;
  count: number;
}

export interface SourceCoverage {
  source_name: string;
  full_content: number;
  metadata_only: number;
}

export interface TopTranslator {
  name: string;
  dynasty: string | null;
  count: number;
}

export interface StatsOverview {
  summary: StatsSummary;
  dynasty_distribution: DynastyDistribution[];
  language_distribution: LanguageDistribution[];
  category_distribution: CategoryDistribution[];
  source_coverage: SourceCoverage[];
  top_translators: TopTranslator[];
}

export interface TimelineItem {
  id: number;
  name_zh: string;
  name_en: string | null;
  dynasty: string | null;
  year_start: number | null;
  year_end: number | null;
  category?: string | null;
  translator?: string | null;
  entity_type?: string | null;
}

export interface TimelineResponse {
  items: TimelineItem[];
  total: number;
}

export type TimelineDimension = "texts" | "figures" | "schools";

export async function getStatsOverview(): Promise<StatsOverview> {
  const { data } = await api.get<StatsOverview>("/stats/overview");
  return data;
}

export async function getStatsTimeline(params: {
  dimension: TimelineDimension;
  category?: string;
  language?: string;
  source_id?: string;
  page?: number;
  page_size?: number;
}): Promise<TimelineResponse> {
  const { data } = await api.get<TimelineResponse>("/stats/timeline", { params });
  return data;
}
```

- [ ] **Step 2: Write the Zustand store**

Create `frontend/src/stores/timelineStore.ts`:

```typescript
import { create } from "zustand";
import type { TimelineDimension } from "../api/stats";

interface TimelineState {
  dimension: TimelineDimension;
  setDimension: (d: TimelineDimension) => void;
  scholarlyMode: boolean;
  toggleScholarlyMode: () => void;
  filters: {
    category: string | null;
    language: string | null;
    sourceId: string | null;
  };
  setFilter: (key: "category" | "language" | "sourceId", value: string | null) => void;
  resetFilters: () => void;
}

export const useTimelineStore = create<TimelineState>()((set) => ({
  dimension: "texts",
  setDimension: (dimension) => set({ dimension }),
  scholarlyMode: false,
  toggleScholarlyMode: () => set((s) => ({ scholarlyMode: !s.scholarlyMode })),
  filters: { category: null, language: null, sourceId: null },
  setFilter: (key, value) =>
    set((s) => ({ filters: { ...s.filters, [key]: value } })),
  resetFilters: () =>
    set({ filters: { category: null, language: null, sourceId: null } }),
}));
```

- [ ] **Step 3: Verify lint passes**

Run: `cd ~/projects/fojin/frontend && npx eslint src/api/stats.ts src/stores/timelineStore.ts`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/stats.ts frontend/src/stores/timelineStore.ts
git commit -m "feat(stats): add stats API client and timeline store"
```

---

### Task 6: Dashboard Page — Summary Cards + Dynasty Bar Chart

**Files:**
- Create: `frontend/src/components/dashboard/SummaryCards.tsx`
- Create: `frontend/src/components/dashboard/DynastyBarChart.tsx`
- Create: `frontend/src/styles/dashboard.css`
- Create: `frontend/src/pages/DashboardPage.tsx` (partial — first two chart sections)

- [ ] **Step 1: Create dashboard styles**

Create `frontend/src/styles/dashboard.css`:

```css
.dashboard-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px 16px;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.dashboard-grid .full-width {
  grid-column: 1 / -1;
}

.dashboard-card {
  background: var(--fj-bg, #f8f5ef);
  border: 1px solid var(--fj-border, #d9d0c1);
  border-radius: 8px;
  padding: 20px;
}

.dashboard-card h3 {
  font-family: "Noto Serif SC", serif;
  color: var(--fj-ink, #2b2318);
  margin-bottom: 16px;
  font-size: 16px;
}

.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}

.summary-card {
  text-align: center;
  padding: 16px 8px;
  background: var(--fj-bg, #f8f5ef);
  border: 1px solid var(--fj-border, #d9d0c1);
  border-radius: 8px;
}

.summary-card .value {
  font-size: 28px;
  font-weight: 700;
  color: var(--fj-accent, #8b2500);
  font-family: "Noto Serif SC", serif;
}

.summary-card .label {
  font-size: 13px;
  color: var(--fj-ink, #2b2318);
  opacity: 0.7;
  margin-top: 4px;
}

.scholarly-label {
  font-size: 11px;
  color: var(--fj-ink, #2b2318);
  opacity: 0.5;
}

@media (max-width: 768px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
  }
  .summary-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}
```

- [ ] **Step 2: Create SummaryCards component**

Create `frontend/src/components/dashboard/SummaryCards.tsx`:

```typescript
import { useTranslation } from "react-i18next";
import type { StatsSummary } from "../../api/stats";

interface Props {
  summary: StatsSummary;
  scholarlyMode: boolean;
}

export default function SummaryCards({ summary, scholarlyMode }: Props) {
  const { t } = useTranslation();
  const cards = [
    { key: "texts", value: summary.total_texts, label: t("dashboard.totalTexts") },
    { key: "sources", value: summary.total_sources, label: t("dashboard.totalSources") },
    { key: "languages", value: summary.total_languages, label: t("dashboard.totalLanguages") },
    { key: "entities", value: summary.total_kg_entities, label: t("dashboard.totalEntities") },
    { key: "relations", value: summary.total_kg_relations, label: t("dashboard.totalRelations") },
    { key: "dict", value: summary.total_dict_entries, label: t("dashboard.totalDictEntries") },
  ];

  return (
    <div className="summary-cards">
      {cards.map((c) => (
        <div key={c.key} className="summary-card">
          <div className="value">{c.value.toLocaleString()}</div>
          <div className="label">{c.label}</div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Create DynastyBarChart component**

Create `frontend/src/components/dashboard/DynastyBarChart.tsx`:

```typescript
import { useEffect, useRef } from "react";
import * as d3 from "d3";
import type { DynastyDistribution } from "../../api/stats";
import { DYNASTIES, resolveDynasty } from "../../data/dynasty_years";

interface Props {
  data: DynastyDistribution[];
  scholarlyMode: boolean;
}

export default function DynastyBarChart({ data, scholarlyMode }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    // Sort by chronological order using DYNASTIES config
    const dynastyOrder = new Map(DYNASTIES.map((d, i) => [d.name_zh, i]));
    const sorted = [...data].sort((a, b) => {
      const ia = dynastyOrder.get(a.dynasty) ?? 999;
      const ib = dynastyOrder.get(b.dynasty) ?? 999;
      return ia - ib;
    });

    const margin = { top: 10, right: scholarlyMode ? 50 : 20, bottom: 30, left: 80 };
    const width = 500 - margin.left - margin.right;
    const height = Math.max(300, sorted.length * 24);

    svg.attr("viewBox", `0 0 ${width + margin.left + margin.right} ${height + margin.top + margin.bottom}`);

    const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

    const y = d3.scaleBand().domain(sorted.map((d) => d.dynasty)).range([0, height]).padding(0.2);
    const x = d3.scaleLinear().domain([0, d3.max(sorted, (d) => d.count) || 1]).range([0, width]);

    g.append("g").call(d3.axisLeft(y).tickSize(0)).select(".domain").remove();

    g.selectAll(".bar")
      .data(sorted)
      .join("rect")
      .attr("class", "bar")
      .attr("y", (d) => y(d.dynasty) || 0)
      .attr("height", y.bandwidth())
      .attr("x", 0)
      .attr("width", (d) => x(d.count))
      .attr("fill", (d) => resolveDynasty(d.dynasty)?.color ?? "#b08d57")
      .attr("rx", 2);

    if (scholarlyMode) {
      g.selectAll(".label")
        .data(sorted)
        .join("text")
        .attr("class", "scholarly-label")
        .attr("y", (d) => (y(d.dynasty) || 0) + y.bandwidth() / 2)
        .attr("x", (d) => x(d.count) + 4)
        .attr("dy", "0.35em")
        .attr("font-size", "11px")
        .text((d) => d.count.toLocaleString());
    }
  }, [data, scholarlyMode]);

  return <svg ref={svgRef} style={{ width: "100%", height: "auto" }} />;
}
```

- [ ] **Step 4: Create initial DashboardPage**

Create `frontend/src/pages/DashboardPage.tsx`:

```typescript
import { useTranslation } from "react-i18next";
import { Helmet } from "react-helmet-async";
import { useQuery } from "@tanstack/react-query";
import { Switch, Spin, Empty } from "antd";
import { useState } from "react";
import { getStatsOverview } from "../api/stats";
import SummaryCards from "../components/dashboard/SummaryCards";
import DynastyBarChart from "../components/dashboard/DynastyBarChart";
import "../styles/dashboard.css";

export default function DashboardPage() {
  const { t } = useTranslation();
  const [scholarlyMode, setScholarlyMode] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["statsOverview"],
    queryFn: getStatsOverview,
    staleTime: 3600000,
  });

  if (isLoading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!data) {
    return <Empty description={t("common.noData")} />;
  }

  return (
    <>
      <Helmet>
        <title>{t("dashboard.title")} - FoJin</title>
      </Helmet>
      <div className="dashboard-container">
        <div className="dashboard-header">
          <h2 style={{ fontFamily: '"Noto Serif SC", serif', color: "var(--fj-ink)" }}>
            {t("dashboard.title")}
          </h2>
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span>{t("dashboard.scholarlyMode")}</span>
            <Switch checked={scholarlyMode} onChange={setScholarlyMode} />
          </label>
        </div>

        <div className="dashboard-grid">
          <div className="dashboard-card full-width">
            <h3>{t("dashboard.platformSummary")}</h3>
            <SummaryCards summary={data.summary} scholarlyMode={scholarlyMode} />
          </div>

          <div className="dashboard-card">
            <h3>{t("dashboard.dynastyDistribution")}</h3>
            <DynastyBarChart data={data.dynasty_distribution} scholarlyMode={scholarlyMode} />
          </div>
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 5: Verify lint passes**

Run: `cd ~/projects/fojin/frontend && npx eslint src/pages/DashboardPage.tsx src/components/dashboard/ src/styles/dashboard.css`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx frontend/src/components/dashboard/SummaryCards.tsx frontend/src/components/dashboard/DynastyBarChart.tsx frontend/src/styles/dashboard.css
git commit -m "feat(dashboard): add dashboard page with summary cards and dynasty chart"
```

---

### Task 7: Dashboard — Remaining Charts

**Files:**
- Create: `frontend/src/components/dashboard/LanguageDonut.tsx`
- Create: `frontend/src/components/dashboard/CategoryTreemap.tsx`
- Create: `frontend/src/components/dashboard/SourceCoverageChart.tsx`
- Create: `frontend/src/components/dashboard/TranslationTrendChart.tsx`
- Create: `frontend/src/components/dashboard/TopTranslatorsChart.tsx`
- Modify: `frontend/src/pages/DashboardPage.tsx`

- [ ] **Step 1: Create LanguageDonut**

Create `frontend/src/components/dashboard/LanguageDonut.tsx` — D3 donut chart showing language distribution, top 10 + "other".

- [ ] **Step 2: Create CategoryTreemap**

Create `frontend/src/components/dashboard/CategoryTreemap.tsx` — D3 treemap of category breakdown.

- [ ] **Step 3: Create SourceCoverageChart**

Create `frontend/src/components/dashboard/SourceCoverageChart.tsx` — D3 horizontal stacked bar (full content vs metadata-only per source).

- [ ] **Step 4: Create TranslationTrendChart**

Create `frontend/src/components/dashboard/TranslationTrendChart.tsx` — D3 area chart showing text count per dynasty as a chronological trend.

- [ ] **Step 5: Create TopTranslatorsChart**

Create `frontend/src/components/dashboard/TopTranslatorsChart.tsx` — D3 horizontal bar chart, top 15 translators by text count.

- [ ] **Step 6: Wire all charts into DashboardPage**

Update `frontend/src/pages/DashboardPage.tsx` to import and render all chart components in the grid layout:
- Row 1: SummaryCards (full-width)
- Row 2: DynastyBarChart + LanguageDonut
- Row 3: CategoryTreemap + SourceCoverageChart
- Row 4: TranslationTrendChart + TopTranslatorsChart

- [ ] **Step 7: Verify lint + TypeScript passes**

Run: `cd ~/projects/fojin/frontend && npx eslint src/components/dashboard/ src/pages/DashboardPage.tsx && npx tsc -b --noEmit`
Expected: no errors

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/dashboard/ frontend/src/pages/DashboardPage.tsx
git commit -m "feat(dashboard): add all chart components — language, category, source, trend, translators"
```

---

### Task 8: Timeline Page — Core Visualization

**Files:**
- Create: `frontend/src/components/timeline/DynastyBands.tsx`
- Create: `frontend/src/components/timeline/TimelineTooltip.tsx`
- Create: `frontend/src/components/timeline/TimelineChart.tsx`
- Create: `frontend/src/components/timeline/TimelineFilters.tsx`
- Create: `frontend/src/styles/timeline.css`
- Create: `frontend/src/pages/TimelinePage.tsx`

- [ ] **Step 1: Create timeline styles**

Create `frontend/src/styles/timeline.css`:

```css
.timeline-container {
  max-width: 1400px;
  margin: 0 auto;
  padding: 16px;
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.timeline-body {
  display: flex;
  gap: 16px;
}

.timeline-filters {
  width: 220px;
  flex-shrink: 0;
  background: var(--fj-bg, #f8f5ef);
  border: 1px solid var(--fj-border, #d9d0c1);
  border-radius: 8px;
  padding: 16px;
  max-height: calc(100vh - 200px);
  overflow-y: auto;
}

.timeline-filters h4 {
  font-family: "Noto Serif SC", serif;
  font-size: 14px;
  margin-bottom: 8px;
  color: var(--fj-ink, #2b2318);
}

.timeline-main {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  background: var(--fj-bg, #f8f5ef);
  border: 1px solid var(--fj-border, #d9d0c1);
  border-radius: 8px;
  padding: 8px;
}

.timeline-tooltip {
  position: absolute;
  pointer-events: none;
  background: rgba(43, 35, 24, 0.9);
  color: #f8f5ef;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  max-width: 280px;
  z-index: 100;
  font-family: "Noto Serif SC", serif;
}

.timeline-tooltip .tt-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.timeline-tooltip .tt-meta {
  opacity: 0.8;
  font-size: 12px;
}

@media (max-width: 768px) {
  .timeline-body {
    flex-direction: column;
  }
  .timeline-filters {
    width: 100%;
    max-height: none;
  }
}
```

- [ ] **Step 2: Create DynastyBands**

Create `frontend/src/components/timeline/DynastyBands.tsx` — renders colored vertical strips behind the timeline. Receives D3 xScale and dynasties config, draws `<rect>` bands with dynasty name labels at top.

- [ ] **Step 3: Create TimelineTooltip**

Create `frontend/src/components/timeline/TimelineTooltip.tsx` — positioned tooltip showing item name, dynasty, translator/entity type. Uses portal or absolute positioning.

- [ ] **Step 4: Create TimelineChart**

Create `frontend/src/components/timeline/TimelineChart.tsx` — main D3 SVG component:
- X axis: year scale (-500 to 2000)
- Dynasty color bands as background (using DynastyBands)
- Nodes: circles for each timeline item, positioned by dynasty year range (deterministic hash-based spread within dynasty range)
- D3 zoom behavior for pan/zoom
- Hover triggers TimelineTooltip
- Click navigates to text detail or KG entity

- [ ] **Step 5: Create TimelineFilters**

Create `frontend/src/components/timeline/TimelineFilters.tsx` — sidebar with:
- Category checkboxes (sutra/vinaya/abhidharma/commentary)
- Language select
- Source select
- Uses `useTimelineStore` for state

- [ ] **Step 6: Create TimelinePage**

Create `frontend/src/pages/TimelinePage.tsx`:

```typescript
import { useTranslation } from "react-i18next";
import { Helmet } from "react-helmet-async";
import { useQuery } from "@tanstack/react-query";
import { Tabs, Switch, Spin, Empty, Pagination } from "antd";
import { useState } from "react";
import { getStatsTimeline } from "../api/stats";
import { useTimelineStore } from "../stores/timelineStore";
import TimelineChart from "../components/timeline/TimelineChart";
import TimelineFilters from "../components/timeline/TimelineFilters";
import "../styles/timeline.css";

export default function TimelinePage() {
  const { t } = useTranslation();
  const { dimension, setDimension, scholarlyMode, toggleScholarlyMode, filters } = useTimelineStore();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ["statsTimeline", dimension, filters, page],
    queryFn: () =>
      getStatsTimeline({
        dimension,
        category: filters.category ?? undefined,
        language: filters.language ?? undefined,
        source_id: filters.sourceId ?? undefined,
        page,
        page_size: 200,
      }),
    staleTime: 3600000,
  });

  return (
    <>
      <Helmet>
        <title>{t("timeline.title")} - FoJin</title>
      </Helmet>
      <div className="timeline-container">
        <div className="timeline-header">
          <h2 style={{ fontFamily: '"Noto Serif SC", serif', color: "var(--fj-ink)" }}>
            {t("timeline.title")}
          </h2>
          <Tabs
            activeKey={dimension}
            onChange={(k) => { setDimension(k as typeof dimension); setPage(1); }}
            items={[
              { key: "texts", label: t("timeline.texts") },
              { key: "figures", label: t("timeline.figures") },
              { key: "schools", label: t("timeline.schools") },
            ]}
          />
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span>{t("dashboard.scholarlyMode")}</span>
            <Switch checked={scholarlyMode} onChange={toggleScholarlyMode} />
          </label>
        </div>
        <div className="timeline-body">
          <TimelineFilters />
          <div className="timeline-main">
            {isLoading ? (
              <div style={{ textAlign: "center", padding: 80 }}><Spin size="large" /></div>
            ) : !data || data.items.length === 0 ? (
              <Empty description={t("common.noData")} />
            ) : (
              <>
                <TimelineChart items={data.items} scholarlyMode={scholarlyMode} />
                {data.total > 200 && (
                  <Pagination
                    current={page}
                    total={data.total}
                    pageSize={200}
                    onChange={setPage}
                    showSizeChanger={false}
                    style={{ marginTop: 16, textAlign: "center" }}
                  />
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 7: Verify lint + TypeScript**

Run: `cd ~/projects/fojin/frontend && npx eslint src/pages/TimelinePage.tsx src/components/timeline/ src/styles/timeline.css && npx tsc -b --noEmit`
Expected: no errors

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/TimelinePage.tsx frontend/src/components/timeline/ frontend/src/styles/timeline.css
git commit -m "feat(timeline): add timeline page with D3 visualization, filters, and dynasty bands"
```

---

### Task 9: Routing, Navigation, and i18n

**Files:**
- Modify: `frontend/src/App.tsx:19-34` (lazy imports) and route definitions
- Modify: `frontend/src/components/Layout.tsx:60` (navItems)
- Modify: `frontend/public/locales/zh/translation.json`
- Modify: `frontend/public/locales/en/translation.json`

- [ ] **Step 1: Add lazy imports and routes in App.tsx**

In `frontend/src/App.tsx`, add after the existing lazy imports (around line 33):

```typescript
const TimelinePage = lazy(() => import("./pages/TimelinePage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
```

Then add routes inside the `<Layout>` routes (look for the pattern of `<Route path="..." element={...} />`):

```typescript
<Route path="/timeline" element={<TimelinePage />} />
<Route path="/dashboard" element={<DashboardPage />} />
```

- [ ] **Step 2: Add nav items in Layout.tsx**

In `frontend/src/components/Layout.tsx`, update the `navItems` array (around line 60). Add two entries — use `FieldTimeOutlined` for timeline and `BarChartOutlined` for dashboard from `@ant-design/icons`. Add the import at the top.

```typescript
{ icon: <FieldTimeOutlined />, label: t("nav.timeline"), path: "/timeline" },
{ icon: <BarChartOutlined />, label: t("nav.dashboard"), path: "/dashboard" },
```

- [ ] **Step 3: Add Chinese i18n keys**

In `frontend/public/locales/zh/translation.json`, add:

```json
"nav.timeline": "历史时间线",
"nav.dashboard": "数据总览",
"timeline.title": "佛典历史时间线",
"timeline.texts": "经文",
"timeline.figures": "人物",
"timeline.schools": "宗派",
"timeline.filterCategory": "分类",
"timeline.filterLanguage": "语言",
"timeline.filterSource": "数据源",
"dashboard.title": "数据总览",
"dashboard.scholarlyMode": "学术模式",
"dashboard.platformSummary": "平台概览",
"dashboard.dynastyDistribution": "朝代分布",
"dashboard.languageDistribution": "语言分布",
"dashboard.categoryBreakdown": "分类构成",
"dashboard.sourceCoverage": "数据源覆盖",
"dashboard.translationTrend": "翻译活动趋势",
"dashboard.topTranslators": "翻译数量排行",
"dashboard.totalTexts": "经文总数",
"dashboard.totalSources": "数据源",
"dashboard.totalLanguages": "语言种类",
"dashboard.totalEntities": "知识实体",
"dashboard.totalRelations": "知识关系",
"dashboard.totalDictEntries": "字典条目"
```

- [ ] **Step 4: Add English i18n keys**

In `frontend/public/locales/en/translation.json`, add corresponding English translations.

- [ ] **Step 5: Verify lint + TypeScript**

Run: `cd ~/projects/fojin/frontend && npx eslint src/App.tsx src/components/Layout.tsx && npx tsc -b --noEmit`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/Layout.tsx frontend/public/locales/zh/translation.json frontend/public/locales/en/translation.json
git commit -m "feat(stats): add routing, navigation, and i18n for timeline and dashboard"
```

---

### Task 10: Integration Testing + Final Verification

**Files:**
- All previously created files

- [ ] **Step 1: Run backend full test suite**

Run: `cd ~/projects/fojin/backend && ruff check app/ && python -m pytest tests/ -v`
Expected: all pass, no lint errors

- [ ] **Step 2: Run frontend full checks**

Run: `cd ~/projects/fojin/frontend && npx eslint src/ && npx tsc -b --noEmit`
Expected: 0 errors on both

- [ ] **Step 3: Verify Vite build succeeds**

Run: `cd ~/projects/fojin/frontend && npx vite build`
Expected: build succeeds with no errors

- [ ] **Step 4: Fix any issues found**

If any lint, type, or build errors were found in steps 1-3, fix them and re-run.

- [ ] **Step 5: Final commit if fixes were needed**

```bash
git add -A
git commit -m "fix: address lint and build issues for timeline and dashboard"
```
