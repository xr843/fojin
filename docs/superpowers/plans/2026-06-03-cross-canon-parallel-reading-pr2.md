# Cross-Canon Parallel Reading PR-2 — AI Difference Analysis Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add "AI 差异分析" capability to the parallel reader — user selects paragraphs across columns → backend LLM call (cached by chunk hash) → popover renders structured analysis.

**Architecture:** New `ai_diff_cache` table (Alembic 0147) keyed by sha256 of sorted chunk identifiers. New `app/services/ai_diff.py` with a versioned locked system prompt + raw httpx call to `settings.llm_api_url` (OpenAI-compatible, same provider fojin uses for `/chat`). New `POST /alignment/ai-diff` FastAPI endpoint. Frontend `AIDiffPopover` lives in `frontend/src/components/parallel/`, triggered by text-selection inside any `AlignmentColumn`.

**Tech Stack:** FastAPI · Alembic · SQLAlchemy 2.x async · httpx · React 19 · Ant Design 5 · @tanstack/react-query · Vitest

**Spec:** `docs/superpowers/specs/2026-06-03-cross-canon-parallel-reading-v1-design.md` (PR-2 section)

---

## File Structure

| File | Role |
|---|---|
| `backend/alembic/versions/0147_add_ai_diff_cache.py` | Create `ai_diff_cache` table with chunks_hash PK + analysis JSON + created_at |
| `backend/app/models/ai_diff_cache.py` | SQLAlchemy ORM model |
| `backend/app/services/ai_diff.py` | LLM call + cache lookup/insert + chunks_hash computation + locked prompt |
| `backend/app/services/ai_diff_prompt.py` | Versioned `SYSTEM_PROMPT_V1` constant in its own module so prompt changes are auditable |
| `backend/app/schemas/ai_diff.py` | Pydantic request/response models |
| `backend/app/api/alignment.py` | Add `POST /alignment/ai-diff` route (extends existing file) |
| `backend/tests/test_ai_diff_service.py` | Unit tests for chunks_hash + cache behavior (LLM call mocked) |
| `backend/tests/test_alignment_ai_diff_endpoint.py` | Endpoint integration test (LLM call mocked) |
| `frontend/src/components/parallel/AIDiffPopover.tsx` | Popover UI: loading / error / rendered analysis sections |
| `frontend/src/components/parallel/AIDiffPopover.test.tsx` | Unit tests for popover states |
| `frontend/src/components/parallel/useSelectedChunks.ts` | Hook: tracks which chunks are selected across all columns |
| `frontend/src/components/parallel/useSelectedChunks.test.ts` | Unit tests for selection state |
| `frontend/src/pages/ParallelReaderPage.tsx` | Wire selection handler + popover trigger (modify) |
| `frontend/src/api/client.ts` | Add `postAiDiff()` client function + types (modify) |
| `frontend/src/styles/parallel.css` | Selection highlight + popover trigger button styles (modify) |

---

## Task 0: Setup PR-2 branch

**Files:** none

- [ ] **Step 0.1: Sync master**

```bash
cd /home/lqsxi/projects/fojin
git checkout master
git pull origin master
```

- [ ] **Step 0.2: Create PR-2 branch**

```bash
git checkout -b feat/parallel-reader-v2-ai-diff
```

---

## Task 1: Alembic migration — `ai_diff_cache` table

**Files:**
- Create: `backend/alembic/versions/0147_add_ai_diff_cache.py`

- [ ] **Step 1.1: Confirm latest migration is 0146**

```bash
ls /home/lqsxi/projects/fojin/backend/alembic/versions/ | sort | tail -3
```

Expected: `0144_…`, `0145_…`, `0146_…`. If 0147+ already exists, bump this migration's number to the next free integer.

- [ ] **Step 1.2: Write the migration**

```python
# backend/alembic/versions/0147_add_ai_diff_cache.py
"""add ai_diff_cache table for cross-canon AI difference analysis

Revision ID: 0147
Revises: 0146
Create Date: 2026-06-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0147"
down_revision: Union[str, None] = "0146"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_diff_cache",
        sa.Column("chunks_hash", sa.String(64), primary_key=True),
        sa.Column("prompt_version", sa.String(20), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("analysis", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_ai_diff_cache_created_at",
        "ai_diff_cache",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_diff_cache_created_at", "ai_diff_cache")
    op.drop_table("ai_diff_cache")
```

- [ ] **Step 1.3: Verify migration syntax with `alembic heads` dry-run**

```bash
cd /home/lqsxi/projects/fojin/backend && python -c "
from alembic.config import Config
from alembic.script import ScriptDirectory
cfg = Config('alembic.ini')
script = ScriptDirectory.from_config(cfg)
print('heads:', script.get_heads())
"
```

Expected: prints `('0147',)` (single head, no branches)

- [ ] **Step 1.4: Commit**

```bash
git add backend/alembic/versions/0147_add_ai_diff_cache.py
git commit -m "feat(alignment): add ai_diff_cache table (Alembic 0147)"
```

---

## Task 2: SQLAlchemy ORM model

**Files:**
- Create: `backend/app/models/ai_diff_cache.py`

- [ ] **Step 2.1: Inspect existing model pattern**

Run:
```bash
head -30 /home/lqsxi/projects/fojin/backend/app/models/text_relation.py 2>/dev/null || ls /home/lqsxi/projects/fojin/backend/app/models/
```

Take note of how an existing simple model imports `Base` and declares columns.

- [ ] **Step 2.2: Write the model**

```python
# backend/app/models/ai_diff_cache.py
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AiDiffCache(Base):
    """Cache of LLM-generated cross-canon difference analyses.

    Keyed by a deterministic hash of (sorted chunk identifiers + prompt_version + model),
    so identical requests reuse the previous analysis verbatim.
    """

    __tablename__ = "ai_diff_cache"

    chunks_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    analysis: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
```

- [ ] **Step 2.3: Register model so Alembic autogenerate sees it (if env.py uses metadata)**

```bash
grep -n "ai_diff_cache\|AiDiffCache" /home/lqsxi/projects/fojin/backend/app/models/__init__.py
```

If not present, edit `backend/app/models/__init__.py` to add:

```python
from app.models.ai_diff_cache import AiDiffCache  # noqa: F401
```

(Match the line style of existing imports — most projects import all models in `__init__.py` for Alembic.)

- [ ] **Step 2.4: Commit**

```bash
git add backend/app/models/ai_diff_cache.py backend/app/models/__init__.py
git commit -m "feat(alignment): add AiDiffCache ORM model"
```

---

## Task 3: Pydantic schemas

**Files:**
- Create: `backend/app/schemas/ai_diff.py`

- [ ] **Step 3.1: Write the schemas**

```python
# backend/app/schemas/ai_diff.py
from pydantic import BaseModel, Field


class AiDiffChunk(BaseModel):
    """One paragraph the user selected for cross-version analysis."""
    text_id: int
    juan_num: int
    chunk_index: int
    lang: str = Field(..., description="One of lzh/pi/sa/bo/en")
    text: str = Field(..., min_length=1, max_length=3000)


class AiDiffRequest(BaseModel):
    chunks: list[AiDiffChunk] = Field(..., min_length=2, max_length=4)


class AiDiffResponse(BaseModel):
    cached: bool
    prompt_version: str
    model: str
    analysis: dict
    """Free-shape analysis object from the LLM. V1 prompt asks for keys:
    `summary` (str), `differences` (list[str]), `doctrinal_notes` (str).
    Stored as JSON; frontend renders defensively.
    """
```

- [ ] **Step 3.2: Commit**

```bash
git add backend/app/schemas/ai_diff.py
git commit -m "feat(alignment): pydantic schemas for ai-diff endpoint"
```

---

## Task 4: Locked system prompt (separate module)

**Files:**
- Create: `backend/app/services/ai_diff_prompt.py`

- [ ] **Step 4.1: Write the prompt module**

```python
# backend/app/services/ai_diff_prompt.py
"""Locked system prompt for cross-canon AI difference analysis.

Versioned: changing the prompt requires bumping PROMPT_VERSION so cached
analyses produced under the old prompt are not silently reused for the new
prompt. The cache is keyed by (chunks_hash, prompt_version), so old entries
remain in place for audit but are not served once the version bumps.
"""

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """你是一位佛教文献跨藏经对照分析的学者助手。

任务：对用户给出的 2-4 个段落（同一经文在不同语言/译本中的对应段落），输出严谨的差异分析。

输出严格使用如下 JSON 结构（不要包含其他键，不要使用 markdown 代码块）：
{
  "summary": "一句话概括三个版本的核心一致性与最关键的差异。中文。",
  "differences": [
    "用一行陈述一处具体差异，引用相关段落原文片段（不超过 12 字）",
    "..."
  ],
  "doctrinal_notes": "如有重要的教义/术语翻译选择差异，简述（中文，1-3 句）；无则留空字符串。"
}

约束：
- differences 数组最多 6 条，最少 1 条。优先报告影响文义的差异，跳过纯抄写/标点。
- 引用片段必须出现在用户给的输入里，禁止编造词句。
- 若信息不足以判断差异，differences 写 ["输入不足，无法可靠判断差异"]，不要猜测。
- 全部中文输出（除非引用的原文本身是巴利/梵/藏/英）。
"""
```

- [ ] **Step 4.2: Commit**

```bash
git add backend/app/services/ai_diff_prompt.py
git commit -m "feat(alignment): locked v1 system prompt for ai-diff (versioned)"
```

---

## Task 5: `ai_diff` service — hash + cache + LLM call (TDD)

**Files:**
- Create: `backend/tests/test_ai_diff_service.py`
- Create: `backend/app/services/ai_diff.py`

- [ ] **Step 5.1: Write the failing tests**

```python
# backend/tests/test_ai_diff_service.py
import hashlib
import json

import pytest

from app.schemas.ai_diff import AiDiffChunk
from app.services.ai_diff import compute_chunks_hash


def chunk(text_id: int, juan: int, idx: int, lang: str = "lzh", text: str = "x") -> AiDiffChunk:
    return AiDiffChunk(text_id=text_id, juan_num=juan, chunk_index=idx, lang=lang, text=text)


class TestComputeChunksHash:
    def test_deterministic_for_same_input(self):
        a = [chunk(100, 1, 0), chunk(200, 1, 5)]
        assert compute_chunks_hash(a, "v1", "deepseek-v4-pro") == compute_chunks_hash(a, "v1", "deepseek-v4-pro")

    def test_order_independent(self):
        a = [chunk(100, 1, 0), chunk(200, 1, 5)]
        b = [chunk(200, 1, 5), chunk(100, 1, 0)]
        assert compute_chunks_hash(a, "v1", "deepseek-v4-pro") == compute_chunks_hash(b, "v1", "deepseek-v4-pro")

    def test_text_change_changes_hash(self):
        a = [chunk(100, 1, 0, text="觀自在")]
        b = [chunk(100, 1, 0, text="观自在")]
        assert compute_chunks_hash(a, "v1", "deepseek-v4-pro") != compute_chunks_hash(b, "v1", "deepseek-v4-pro")

    def test_prompt_version_changes_hash(self):
        a = [chunk(100, 1, 0)]
        assert compute_chunks_hash(a, "v1", "deepseek-v4-pro") != compute_chunks_hash(a, "v2", "deepseek-v4-pro")

    def test_model_changes_hash(self):
        a = [chunk(100, 1, 0)]
        assert compute_chunks_hash(a, "v1", "deepseek-v4-pro") != compute_chunks_hash(a, "v1", "gpt-4o-mini")

    def test_returns_64_char_hex(self):
        h = compute_chunks_hash([chunk(100, 1, 0)], "v1", "deepseek-v4-pro")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
```

- [ ] **Step 5.2: Run tests to verify they fail**

```bash
cd /home/lqsxi/projects/fojin/backend && uv run pytest tests/services/test_ai_diff.py -v 2>&1 | tail -10
```

Expected: collection FAIL with "ImportError: cannot import name 'compute_chunks_hash'"

- [ ] **Step 5.3: Write service module with hash function**

```python
# backend/app/services/ai_diff.py
"""Cross-canon AI difference analysis service.

Computes a deterministic cache key from the selected chunks + prompt
version + model so identical selections return cached analyses
verbatim. New analyses are produced by calling the server-side LLM
(settings.llm_api_url, OpenAI-compatible) with a locked system prompt.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.ai_diff_cache import AiDiffCache
from app.schemas.ai_diff import AiDiffChunk
from app.services.ai_diff_prompt import PROMPT_VERSION, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def compute_chunks_hash(
    chunks: list[AiDiffChunk], prompt_version: str, model: str
) -> str:
    """Deterministic order-independent hash.

    We canonicalise chunks by sorting on (text_id, juan_num, chunk_index)
    then JSON-dumping with sorted keys, so equivalent selections produced
    in different orders share a cache row.
    """
    normalised = sorted(
        (
            {
                "text_id": c.text_id,
                "juan_num": c.juan_num,
                "chunk_index": c.chunk_index,
                "lang": c.lang,
                "text": c.text,
            }
            for c in chunks
        ),
        key=lambda c: (c["text_id"], c["juan_num"], c["chunk_index"]),
    )
    payload = json.dumps(
        {"chunks": normalised, "prompt_version": prompt_version, "model": model},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def get_or_create_diff(
    db: AsyncSession, chunks: list[AiDiffChunk]
) -> tuple[bool, str, str, dict[str, Any]]:
    """Return (cached, prompt_version, model, analysis).

    `cached=True` means the row was served from `ai_diff_cache`.
    `cached=False` means a fresh LLM call was made and the row was inserted.
    """
    model = _resolve_model()
    digest = compute_chunks_hash(chunks, PROMPT_VERSION, model)

    cached = await db.scalar(select(AiDiffCache).where(AiDiffCache.chunks_hash == digest))
    if cached is not None:
        return True, cached.prompt_version, cached.model, cached.analysis

    analysis = await _call_llm(chunks, model)

    row = AiDiffCache(
        chunks_hash=digest,
        prompt_version=PROMPT_VERSION,
        model=model,
        analysis=analysis,
    )
    db.add(row)
    await db.commit()
    return False, PROMPT_VERSION, model, analysis


def _resolve_model() -> str:
    """Server-side default model — same source as chat fallback path."""
    return getattr(settings, "llm_default_model", None) or "deepseek-v4-pro"


async def _call_llm(chunks: list[AiDiffChunk], model: str) -> dict[str, Any]:
    """Single non-streaming OpenAI-compatible chat.completions call.

    Returns the parsed JSON analysis object. Raises on HTTP error.
    """
    base = (settings.llm_api_url or "https://api.deepseek.com/v1").rstrip("/")
    key = settings.llm_api_key
    if not key:
        raise RuntimeError("ai_diff: settings.llm_api_key not configured")

    user_payload_lines = []
    for i, c in enumerate(chunks, 1):
        user_payload_lines.append(
            f"[版本 {i}] text_id={c.text_id} juan={c.juan_num} chunk={c.chunk_index} lang={c.lang}\n{c.text}"
        )
    user_msg = "\n\n".join(user_payload_lines)

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.2,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{base}/chat/completions", headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

    raw = data["choices"][0]["message"]["content"]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("ai_diff: LLM returned non-JSON content, wrapping as raw text")
        return {"summary": raw, "differences": [], "doctrinal_notes": ""}
```

- [ ] **Step 5.4: Run tests to verify they pass**

```bash
cd /home/lqsxi/projects/fojin/backend && uv run pytest tests/services/test_ai_diff.py -v 2>&1 | tail -10
```

Expected: PASS (6 tests)

- [ ] **Step 5.5: Commit**

```bash
git add backend/tests/test_ai_diff_service.py backend/app/services/ai_diff.py
git commit -m "feat(alignment): ai_diff service — hash + cache + LLM call"
```

---

## Task 6: `POST /alignment/ai-diff` endpoint + tests

**Files:**
- Modify: `backend/app/api/alignment.py` (append route)
- Create: `backend/tests/test_alignment_ai_diff_endpoint.py`

- [ ] **Step 6.1: Write the failing endpoint test**

```python
# backend/tests/test_alignment_ai_diff_endpoint.py
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ai_diff_returns_analysis(client: AsyncClient):
    """Endpoint returns analysis from cache or fresh LLM call."""
    body = {
        "chunks": [
            {"text_id": 100, "juan_num": 1, "chunk_index": 0, "lang": "lzh", "text": "觀自在菩薩。"},
            {"text_id": 200, "juan_num": 1, "chunk_index": 0, "lang": "en", "text": "Avalokiteshvara Bodhisattva."},
        ]
    }
    fake_analysis = {
        "summary": "中英两版核心一致。",
        "differences": ["lzh 用观自在，en 用 Avalokiteshvara 音译"],
        "doctrinal_notes": "",
    }
    with patch(
        "app.api.alignment.get_or_create_diff",
        new=AsyncMock(return_value=(False, "v1", "deepseek-v4-pro", fake_analysis)),
    ):
        resp = await client.post("/alignment/ai-diff", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["cached"] is False
    assert data["prompt_version"] == "v1"
    assert data["model"] == "deepseek-v4-pro"
    assert data["analysis"]["summary"] == "中英两版核心一致。"


@pytest.mark.asyncio
async def test_ai_diff_rejects_too_few_chunks(client: AsyncClient):
    body = {"chunks": [{"text_id": 100, "juan_num": 1, "chunk_index": 0, "lang": "lzh", "text": "x"}]}
    resp = await client.post("/alignment/ai-diff", json=body)
    assert resp.status_code == 422  # pydantic min_length=2


@pytest.mark.asyncio
async def test_ai_diff_rejects_too_many_chunks(client: AsyncClient):
    body = {
        "chunks": [
            {"text_id": i, "juan_num": 1, "chunk_index": 0, "lang": "lzh", "text": "x"} for i in range(5)
        ]
    }
    resp = await client.post("/alignment/ai-diff", json=body)
    assert resp.status_code == 422
```

- [ ] **Step 6.2: Run tests to verify they fail**

```bash
cd /home/lqsxi/projects/fojin/backend && uv run pytest tests/api/test_alignment_ai_diff.py -v 2>&1 | tail -10
```

Expected: 3 failures with 404 (route not registered yet).

- [ ] **Step 6.3: Append the endpoint to `backend/app/api/alignment.py`**

Append at end of `backend/app/api/alignment.py`:

```python
from app.schemas.ai_diff import AiDiffRequest, AiDiffResponse
from app.services.ai_diff import get_or_create_diff


@router.post("/ai-diff", response_model=AiDiffResponse)
async def ai_diff(
    payload: AiDiffRequest,
    db: AsyncSession = Depends(get_db),
) -> AiDiffResponse:
    """Generate (or fetch cached) cross-canon difference analysis for 2-4 selected chunks."""
    cached, prompt_version, model, analysis = await get_or_create_diff(db, payload.chunks)
    return AiDiffResponse(
        cached=cached,
        prompt_version=prompt_version,
        model=model,
        analysis=analysis,
    )
```

- [ ] **Step 6.4: Run tests to verify they pass**

```bash
cd /home/lqsxi/projects/fojin/backend && uv run pytest tests/api/test_alignment_ai_diff.py -v 2>&1 | tail -10
```

Expected: PASS (3 tests)

- [ ] **Step 6.5: Run full backend test suite to confirm no regressions**

```bash
cd /home/lqsxi/projects/fojin/backend && uv run pytest 2>&1 | tail -5
```

Expected: all tests PASS (or same pass/skip count as `master`)

- [ ] **Step 6.6: Commit**

```bash
git add backend/app/api/alignment.py backend/tests/test_alignment_ai_diff_endpoint.py
git commit -m "feat(alignment): POST /alignment/ai-diff endpoint (cached + LLM-backed)"
```

---

## Task 7: Frontend API client function

**Files:**
- Modify: `frontend/src/api/client.ts` (append)

- [ ] **Step 7.1: Append the client function and types**

Append to `frontend/src/api/client.ts` (next to other alignment helpers):

```typescript
export interface AiDiffChunkInput {
  text_id: number;
  juan_num: number;
  chunk_index: number;
  lang: string;
  text: string;
}

export interface AiDiffAnalysis {
  summary?: string;
  differences?: string[];
  doctrinal_notes?: string;
}

export interface AiDiffResponse {
  cached: boolean;
  prompt_version: string;
  model: string;
  analysis: AiDiffAnalysis;
}

export async function postAiDiff(chunks: AiDiffChunkInput[]): Promise<AiDiffResponse> {
  const { data } = await api.post<AiDiffResponse>("/alignment/ai-diff", { chunks });
  return data;
}
```

- [ ] **Step 7.2: Verify tsc clean**

```bash
cd /home/lqsxi/projects/fojin/frontend && npx tsc -b --noEmit
```

Expected: no errors

- [ ] **Step 7.3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat(parallel): add postAiDiff client + types"
```

---

## Task 8: `useSelectedChunks` hook (TDD)

**Files:**
- Create: `frontend/src/components/parallel/useSelectedChunks.test.ts`
- Create: `frontend/src/components/parallel/useSelectedChunks.ts`

- [ ] **Step 8.1: Write the failing test**

```typescript
// frontend/src/components/parallel/useSelectedChunks.test.ts
import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSelectedChunks } from "./useSelectedChunks";

describe("useSelectedChunks", () => {
  it("starts empty", () => {
    const { result } = renderHook(() => useSelectedChunks());
    expect(result.current.selected).toEqual([]);
  });

  it("toggles a chunk on / off", () => {
    const { result } = renderHook(() => useSelectedChunks());
    const c = { text_id: 100, juan_num: 1, chunk_index: 0, lang: "lzh", text: "觀" };
    act(() => result.current.toggle(c));
    expect(result.current.selected).toHaveLength(1);
    act(() => result.current.toggle(c));
    expect(result.current.selected).toHaveLength(0);
  });

  it("dedupes by (text_id, chunk_index)", () => {
    const { result } = renderHook(() => useSelectedChunks());
    const c1 = { text_id: 100, juan_num: 1, chunk_index: 0, lang: "lzh", text: "觀" };
    const c1Dup = { ...c1, text: "觀X" }; // text changed but same identity
    act(() => result.current.toggle(c1));
    act(() => result.current.toggle(c1Dup));
    expect(result.current.selected).toHaveLength(0); // second toggle removes the first
  });

  it("clear() empties selection", () => {
    const { result } = renderHook(() => useSelectedChunks());
    const a = { text_id: 100, juan_num: 1, chunk_index: 0, lang: "lzh", text: "觀" };
    const b = { text_id: 200, juan_num: 1, chunk_index: 0, lang: "en", text: "Av" };
    act(() => result.current.toggle(a));
    act(() => result.current.toggle(b));
    expect(result.current.selected).toHaveLength(2);
    act(() => result.current.clear());
    expect(result.current.selected).toHaveLength(0);
  });
});
```

- [ ] **Step 8.2: Run test to verify it fails**

```bash
cd /home/lqsxi/projects/fojin/frontend && npx vitest run src/components/parallel/useSelectedChunks.test.ts 2>&1 | tail -8
```

Expected: FAIL with "Cannot find module './useSelectedChunks'"

- [ ] **Step 8.3: Write the hook**

```typescript
// frontend/src/components/parallel/useSelectedChunks.ts
import { useCallback, useState } from "react";
import type { AiDiffChunkInput } from "../../api/client";

export interface UseSelectedChunksReturn {
  selected: AiDiffChunkInput[];
  toggle: (c: AiDiffChunkInput) => void;
  clear: () => void;
}

function sameChunk(a: AiDiffChunkInput, b: AiDiffChunkInput): boolean {
  return a.text_id === b.text_id && a.chunk_index === b.chunk_index;
}

export function useSelectedChunks(): UseSelectedChunksReturn {
  const [selected, setSelected] = useState<AiDiffChunkInput[]>([]);

  const toggle = useCallback((c: AiDiffChunkInput) => {
    setSelected((prev) => {
      const i = prev.findIndex((p) => sameChunk(p, c));
      if (i >= 0) return prev.filter((_, j) => j !== i);
      return [...prev, c];
    });
  }, []);

  const clear = useCallback(() => setSelected([]), []);

  return { selected, toggle, clear };
}
```

- [ ] **Step 8.4: Run tests to verify they pass**

```bash
cd /home/lqsxi/projects/fojin/frontend && npx vitest run src/components/parallel/useSelectedChunks.test.ts 2>&1 | tail -8
```

Expected: PASS (4 tests)

- [ ] **Step 8.5: Commit**

```bash
git add frontend/src/components/parallel/useSelectedChunks.ts frontend/src/components/parallel/useSelectedChunks.test.ts
git commit -m "feat(parallel): useSelectedChunks hook for cross-column selection"
```

---

## Task 9: `AIDiffPopover` component (TDD)

**Files:**
- Create: `frontend/src/components/parallel/AIDiffPopover.test.tsx`
- Create: `frontend/src/components/parallel/AIDiffPopover.tsx`

- [ ] **Step 9.1: Write the failing test**

```tsx
// frontend/src/components/parallel/AIDiffPopover.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AIDiffPopover from "./AIDiffPopover";
import type { AiDiffChunkInput, AiDiffResponse } from "../../api/client";

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

const chunks: AiDiffChunkInput[] = [
  { text_id: 100, juan_num: 1, chunk_index: 0, lang: "lzh", text: "觀自在菩薩。" },
  { text_id: 200, juan_num: 1, chunk_index: 0, lang: "en", text: "Avalokiteshvara." },
];

describe("AIDiffPopover", () => {
  it("renders loading state while fetching", () => {
    const fetcher = vi.fn(
      () => new Promise<AiDiffResponse>(() => {}), // never resolves
    );
    render(wrap(<AIDiffPopover chunks={chunks} onClose={() => {}} fetchAiDiff={fetcher} />));
    expect(screen.getByText(/正在生成差异分析/)).toBeTruthy();
  });

  it("renders analysis sections on success", async () => {
    const response: AiDiffResponse = {
      cached: false,
      prompt_version: "v1",
      model: "deepseek-v4-pro",
      analysis: {
        summary: "两版核心一致。",
        differences: ["lzh 用观自在", "en 用音译"],
        doctrinal_notes: "无重要教义差异。",
      },
    };
    const fetcher = vi.fn(() => Promise.resolve(response));
    render(wrap(<AIDiffPopover chunks={chunks} onClose={() => {}} fetchAiDiff={fetcher} />));
    await waitFor(() => expect(screen.getByText(/两版核心一致/)).toBeTruthy());
    expect(screen.getByText(/lzh 用观自在/)).toBeTruthy();
    expect(screen.getByText(/无重要教义差异/)).toBeTruthy();
  });

  it("renders error state on failure", async () => {
    const fetcher = vi.fn(() => Promise.reject(new Error("boom")));
    render(wrap(<AIDiffPopover chunks={chunks} onClose={() => {}} fetchAiDiff={fetcher} />));
    await waitFor(() => expect(screen.getByText(/分析失败/)).toBeTruthy());
  });

  it("renders cached badge when response.cached is true", async () => {
    const response: AiDiffResponse = {
      cached: true,
      prompt_version: "v1",
      model: "deepseek-v4-pro",
      analysis: { summary: "x", differences: [], doctrinal_notes: "" },
    };
    const fetcher = vi.fn(() => Promise.resolve(response));
    render(wrap(<AIDiffPopover chunks={chunks} onClose={() => {}} fetchAiDiff={fetcher} />));
    await waitFor(() => expect(screen.getByText(/缓存/)).toBeTruthy());
  });
});
```

- [ ] **Step 9.2: Run test to verify it fails**

```bash
cd /home/lqsxi/projects/fojin/frontend && npx vitest run src/components/parallel/AIDiffPopover.test.tsx 2>&1 | tail -8
```

Expected: FAIL with "Cannot find module './AIDiffPopover'"

- [ ] **Step 9.3: Write the component**

```tsx
// frontend/src/components/parallel/AIDiffPopover.tsx
import { Card, Tag, Spin, Alert, Button } from "antd";
import { CloseOutlined, RobotOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { postAiDiff, type AiDiffChunkInput, type AiDiffResponse } from "../../api/client";

interface Props {
  chunks: AiDiffChunkInput[];
  onClose: () => void;
  /** Override for testing; defaults to postAiDiff. */
  fetchAiDiff?: (chunks: AiDiffChunkInput[]) => Promise<AiDiffResponse>;
}

function chunksKey(chunks: AiDiffChunkInput[]): string {
  return chunks
    .map((c) => `${c.text_id}-${c.juan_num}-${c.chunk_index}`)
    .sort()
    .join("|");
}

export default function AIDiffPopover({ chunks, onClose, fetchAiDiff = postAiDiff }: Props) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["ai-diff", chunksKey(chunks)],
    queryFn: () => fetchAiDiff(chunks),
    enabled: chunks.length >= 2,
    staleTime: 60 * 60 * 1000,
    retry: false,
  });

  return (
    <Card
      className="ai-diff-popover"
      size="small"
      title={
        <div className="ai-diff-popover-header">
          <RobotOutlined /> <span>AI 差异分析</span>
          {data?.cached && <Tag color="default">缓存</Tag>}
          <Button
            type="text"
            size="small"
            icon={<CloseOutlined />}
            onClick={onClose}
            aria-label="关闭"
            style={{ marginLeft: "auto" }}
          />
        </div>
      }
    >
      {isLoading && (
        <div style={{ textAlign: "center", padding: 24 }}>
          <Spin />
          <div style={{ marginTop: 8, color: "#888", fontSize: 13 }}>正在生成差异分析…</div>
        </div>
      )}
      {isError && (
        <Alert
          type="error"
          showIcon
          message="分析失败"
          description="请稍后重试。"
          style={{ margin: "8px 0" }}
        />
      )}
      {data && (
        <div className="ai-diff-popover-body">
          {data.analysis.summary && (
            <p className="ai-diff-summary">{data.analysis.summary}</p>
          )}
          {data.analysis.differences && data.analysis.differences.length > 0 && (
            <>
              <div className="ai-diff-section-label">差异</div>
              <ul className="ai-diff-differences">
                {data.analysis.differences.map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>
            </>
          )}
          {data.analysis.doctrinal_notes && (
            <>
              <div className="ai-diff-section-label">教义注</div>
              <p className="ai-diff-doctrinal">{data.analysis.doctrinal_notes}</p>
            </>
          )}
          <div className="ai-diff-meta">
            <span>{data.model}</span>
            <span style={{ marginLeft: 8 }}>prompt {data.prompt_version}</span>
          </div>
        </div>
      )}
    </Card>
  );
}
```

- [ ] **Step 9.4: Run tests to verify they pass**

```bash
cd /home/lqsxi/projects/fojin/frontend && npx vitest run src/components/parallel/AIDiffPopover.test.tsx 2>&1 | tail -8
```

Expected: PASS (4 tests)

- [ ] **Step 9.5: Commit**

```bash
git add frontend/src/components/parallel/AIDiffPopover.tsx frontend/src/components/parallel/AIDiffPopover.test.tsx
git commit -m "feat(parallel): AIDiffPopover UI (loading/error/cached/rendered states)"
```

---

## Task 10: Extend `parallel.css` with selection + popover styles

**Files:**
- Modify: `frontend/src/styles/parallel.css` (append)

- [ ] **Step 10.1: Append styles**

Add at the END of `frontend/src/styles/parallel.css`:

```css
/* === V2 paragraph selection + AI diff popover === */
.parallel-paragraph.is-selected {
  background-color: rgba(91, 140, 107, 0.18);
  outline: 1px solid rgba(91, 140, 107, 0.45);
  outline-offset: 1px;
  border-radius: 2px;
}

.ai-diff-trigger {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1100;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
}

.ai-diff-popover {
  position: fixed;
  bottom: 88px;
  left: 50%;
  transform: translateX(-50%);
  width: 560px;
  max-width: calc(100vw - 32px);
  max-height: 60vh;
  overflow-y: auto;
  z-index: 1101;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
}

.ai-diff-popover-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ai-diff-summary {
  margin: 0 0 12px 0;
  font-size: 14px;
  line-height: 1.7;
  color: #222;
}

.ai-diff-section-label {
  font-size: 12px;
  color: #5b8c6b;
  font-weight: 500;
  margin: 8px 0 4px 0;
}

.ai-diff-differences {
  margin: 0 0 12px 0;
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.7;
  color: #333;
}

.ai-diff-doctrinal {
  margin: 0 0 12px 0;
  font-size: 13px;
  line-height: 1.7;
  color: #333;
}

.ai-diff-meta {
  border-top: 1px solid #f0f0f0;
  padding-top: 8px;
  font-size: 11px;
  color: #999;
}
```

- [ ] **Step 10.2: Commit**

```bash
git add frontend/src/styles/parallel.css
git commit -m "feat(parallel): V2 selection + AI diff popover styles"
```

---

## Task 11: Wire selection + popover into `ParallelReaderPage`

**Files:**
- Modify: `frontend/src/components/parallel/AlignmentColumn.tsx`
- Modify: `frontend/src/pages/ParallelReaderPage.tsx`

- [ ] **Step 11.1: Extend `AlignmentColumn` to emit chunk-click**

Replace the `<p>` rendering block in `AlignmentColumn.tsx` to accept `selectedKeys` and `onChunkClick`. Insert new props and rendering:

```tsx
// add to Props
  selectedKeys?: Set<string>;
  onChunkClick?: (chunkIndex: number, paragraph: string) => void;
```

Replace the current paragraphs render block:

```tsx
        {paragraphs.map((p, i) => {
          const idx = chunkIndexFor(p, chunkIndex);
          const key = idx !== null ? `${text.text_id}:${idx}` : "";
          const isSelected = idx !== null && selectedKeys?.has(key);
          return (
            <p
              key={i}
              className={`parallel-paragraph${isSelected ? " is-selected" : ""}`}
              data-chunk-index={idx ?? undefined}
              lang={text.lang}
              onClick={() => idx !== null && onChunkClick?.(idx, p)}
              style={onChunkClick && idx !== null ? { cursor: "pointer" } : undefined}
            >
              {p}
            </p>
          );
        })}
```

Update destructuring at top of component:

```tsx
export default function AlignmentColumn({
  text, alignment, scrollRef, selectedKeys, onChunkClick,
}: Props) {
```

- [ ] **Step 11.2: Wire `useSelectedChunks` + `AIDiffPopover` in `ParallelReaderPage`**

Add imports at top of `ParallelReaderPage.tsx`:

```tsx
import { useState } from "react";
import AIDiffPopover from "../components/parallel/AIDiffPopover";
import { useSelectedChunks } from "../components/parallel/useSelectedChunks";
import type { AiDiffChunkInput } from "../api/client";
```

Inside the component, after `useSyncScroll(scrollRefs, alignmentMap);`, add:

```tsx
  const { selected, toggle, clear } = useSelectedChunks();
  const [showDiff, setShowDiff] = useState(false);

  const selectedKeys = new Set(selected.map((s) => `${s.text_id}:${s.chunk_index}`));

  const handleChunkClick = (textId: number, lang: string, juanNum: number, chunkIndex: number, paragraph: string) => {
    const c: AiDiffChunkInput = { text_id: textId, juan_num: juanNum, chunk_index: chunkIndex, lang, text: paragraph };
    toggle(c);
  };
```

In the column render block, change the `<AlignmentColumn>` JSX to pass new props:

```tsx
              <AlignmentColumn
                key={col.text.text_id}
                text={col.text}
                alignment={col.alignment}
                scrollRef={(el) => {
                  scrollRefs.current[i] = { textId: col.text.text_id, el };
                }}
                selectedKeys={selectedKeys}
                onChunkClick={(idx, p) =>
                  handleChunkClick(col.text.text_id, col.text.lang, col.text.juan_num, idx, p)
                }
              />
```

After the `</div>` closing `parallel-grid-v1`, before the page wrapper closes, add the trigger button + popover:

```tsx
          {selected.length >= 2 && !showDiff && (
            <Button
              type="primary"
              size="large"
              shape="round"
              icon={<RobotOutlined />}
              className="ai-diff-trigger"
              onClick={() => setShowDiff(true)}
            >
              AI 差异分析（{selected.length} 段）
            </Button>
          )}
          {showDiff && selected.length >= 2 && (
            <AIDiffPopover
              chunks={selected}
              onClose={() => {
                setShowDiff(false);
                clear();
              }}
            />
          )}
```

Also import `RobotOutlined`:

```tsx
import { ArrowLeftOutlined, RobotOutlined, SwapOutlined } from "@ant-design/icons";
```

- [ ] **Step 11.3: Run tsc + eslint + tests**

```bash
cd /home/lqsxi/projects/fojin/frontend && npx tsc -b --noEmit
cd /home/lqsxi/projects/fojin/frontend && npx eslint src/components/parallel/ src/pages/ParallelReaderPage.tsx
cd /home/lqsxi/projects/fojin/frontend && npx vitest run src/components/parallel/
```

Expected: tsc clean, eslint clean (or only pre-existing warnings), all parallel tests PASS.

- [ ] **Step 11.4: Commit**

```bash
git add frontend/src/components/parallel/AlignmentColumn.tsx frontend/src/pages/ParallelReaderPage.tsx
git commit -m "feat(parallel): wire paragraph-click selection + AI diff popover trigger"
```

---

## Task 12: Full test sweep before PR

**Files:** none

- [ ] **Step 12.1: Frontend full suite**

```bash
cd /home/lqsxi/projects/fojin/frontend && npx vitest run 2>&1 | tail -8
```

Expected: all tests PASS, count = previous (99) + 8 new (4 useSelectedChunks + 4 AIDiffPopover) = 107

- [ ] **Step 12.2: Backend full suite**

```bash
cd /home/lqsxi/projects/fojin/backend && uv run pytest 2>&1 | tail -8
```

Expected: all tests PASS

- [ ] **Step 12.3: If anything fails, fix and re-commit before pushing**

---

## Task 13: Push + open PR

**Files:** none

- [ ] **Step 13.1: Push**

```bash
cd /home/lqsxi/projects/fojin && git push -u origin feat/parallel-reader-v2-ai-diff
```

- [ ] **Step 13.2: Open PR**

```bash
gh pr create --base master --head feat/parallel-reader-v2-ai-diff --title "feat(parallel): V2 cross-canon AI difference analysis" --body "$(cat <<'EOF'
## Summary
- New \`POST /alignment/ai-diff\` endpoint: 2-4 chunks → cached LLM-backed structured difference analysis
- New \`ai_diff_cache\` table (Alembic 0147) keyed by deterministic chunks_hash; identical selections reuse the cached analysis verbatim
- Locked system prompt versioned in \`app/services/ai_diff_prompt.py\` — prompt changes bump version and invalidate cache hits
- Frontend: paragraph-click selection across columns + floating trigger when 2+ chunks selected + \`AIDiffPopover\` rendering summary / differences / doctrinal notes

## Design
\`docs/superpowers/specs/2026-06-03-cross-canon-parallel-reading-v1-design.md\` (PR-2 section)
\`docs/superpowers/plans/2026-06-03-cross-canon-parallel-reading-pr2.md\`

## Test plan
- [x] Backend: \`compute_chunks_hash\` (6 tests: determinism, order, text, prompt, model, hex shape)
- [x] Backend: \`/alignment/ai-diff\` endpoint (3 tests: success, too-few, too-many)
- [x] Frontend: \`useSelectedChunks\` (4 tests: empty, toggle, dedupe, clear)
- [x] Frontend: \`AIDiffPopover\` (4 tests: loading, success, error, cached badge)
- [x] Full backend suite pass
- [x] Full frontend suite pass (107 tests = 99 PR-1 + 8 new)
- [x] tsc + eslint clean
- [ ] Browser smoke post-merge: select 2 paragraphs across columns → click trigger → analysis renders

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 13.3: Verify PR + initial CI**

```bash
gh pr view --json url,statusCheckRollup --jq '{url, checks: [.statusCheckRollup[]? | {name, status, conclusion}]}'
```

---

## Done criteria for PR-2

- All new unit tests pass (6 backend hash + 3 backend endpoint + 4 frontend hook + 4 frontend popover = 17 new)
- Full backend + frontend suites green
- tsc + eslint clean on touched files
- PR opened, CI green
- `Alembic upgrade head (dry-run)` CI check passes (validates new 0147 migration chain)
- Backend smoke validates the new endpoint

## What ships next (PR-3 — separate plan)

- Export current parallel view as markdown
- Shareable deep link with anchor (?anchor=chunk_X)
- Bookmark this view (uses existing bookmark API)
- /parallel route SEO title (audit follow-up from PR-1)
