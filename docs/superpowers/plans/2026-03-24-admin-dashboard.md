# Admin Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin dashboard with overview stats, user management, and annotation review pages.

**Architecture:** New backend module `backend/app/api/admin.py` with all admin endpoints protected by `require_role("admin")`. New service `backend/app/services/admin_service.py` for query logic. Three new frontend pages under `/admin/*` with Ant Design components. Alembic migration adds `last_active_at` column to users table. Middleware updates `last_active_at` with 5-minute throttling.

**Tech Stack:** FastAPI + SQLAlchemy async (backend), React 18 + Ant Design 5 + @ant-design/charts (frontend), PostgreSQL (database), Redis (caching)

**Spec:** `docs/superpowers/specs/2026-03-24-admin-dashboard-design.md`

---

## File Structure

**Backend — Create:**
- `backend/app/api/admin.py` — Admin API router (stats overview, trends, user list, user update, annotation list)
- `backend/app/services/admin_service.py` — Admin query logic (stats aggregation, user queries)
- `backend/app/schemas/admin.py` — Pydantic schemas for admin endpoints
- `backend/alembic/versions/0099_add_user_last_active_at.py` — Migration: add `last_active_at` column
- `backend/tests/test_admin.py` — Admin API tests

**Backend — Modify:**
- `backend/app/models/user.py` — Add `last_active_at` field to User model
- `backend/app/main.py` — Register admin router, add LastActiveMiddleware

**Frontend — Create:**
- `frontend/src/pages/AdminDashboardPage.tsx` — Overview stats page (cards + charts)
- `frontend/src/pages/AdminUsersPage.tsx` — User management table
- `frontend/src/pages/AdminAnnotationsPage.tsx` — Annotation review table

**Frontend — Modify:**
- `frontend/src/api/client.ts` — Add admin API methods and types
- `frontend/src/App.tsx` — Add admin routes
- `frontend/src/components/Layout.tsx` — Admin sub-menu navigation
- `frontend/public/locales/zh/translation.json` — Chinese admin labels
- `frontend/public/locales/en/translation.json` — English admin labels

---

## Task 1: Database Migration — Add `last_active_at` to Users

**Files:**
- Modify: `backend/app/models/user.py:18-24`
- Create: `backend/alembic/versions/0099_add_user_last_active_at.py`

- [ ] **Step 1: Add `last_active_at` to User model**

In `backend/app/models/user.py`, add after the `updated_at` field (line 24):

```python
last_active_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), nullable=True
)
```

- [ ] **Step 2: Create alembic migration**

```bash
cd backend && alembic revision --autogenerate -m "add user last_active_at" --rev-id 0099
```

Verify the generated migration contains `op.add_column('users', sa.Column('last_active_at', ...))`.

- [ ] **Step 3: Run migration**

```bash
cd backend && alembic upgrade head
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/user.py backend/alembic/versions/0099_add_user_last_active_at.py
git commit -m "feat(admin): add last_active_at column to users table"
```

---

## Task 2: Backend — Admin Schemas

**Files:**
- Create: `backend/app/schemas/admin.py`

- [ ] **Step 1: Create admin schemas**

Create `backend/app/schemas/admin.py`:

```python
from datetime import datetime

from pydantic import BaseModel, Field


class AdminOverview(BaseModel):
    total_users: int
    new_users_today: int
    total_sessions: int
    new_sessions_today: int
    total_messages: int
    new_messages_today: int
    pending_suggestions: int
    pending_annotations: int


class DailyCount(BaseModel):
    date: str
    count: int


class AdminTrends(BaseModel):
    registrations: list[DailyCount]
    messages: list[DailyCount]
    active_users: list[DailyCount]


class AdminUserItem(BaseModel):
    id: int
    username: str
    display_name: str | None
    email: str
    role: str
    is_active: bool
    created_at: datetime
    last_active_at: datetime | None

    model_config = {"from_attributes": True}


class AdminUserUpdate(BaseModel):
    role: str | None = Field(None, pattern="^(user|reviewer|admin)$")
    is_active: bool | None = None


class AdminUserListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[AdminUserItem]


class AdminAnnotationItem(BaseModel):
    id: int
    text_id: int
    juan_num: int
    annotation_type: str
    content: str
    user_id: int
    username: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminAnnotationListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[AdminAnnotationItem]
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/admin.py
git commit -m "feat(admin): add Pydantic schemas for admin endpoints"
```

---

## Task 3: Backend — Admin Service

**Files:**
- Create: `backend/app/services/admin_service.py`

- [ ] **Step 1: Create admin service**

Create `backend/app/services/admin_service.py`:

```python
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Date, case, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.annotation import Annotation
from app.models.chat import ChatMessage, ChatSession
from app.models.source import SourceSuggestion
from app.models.user import ReadingHistory, User
from app.schemas.admin import AdminAnnotationItem, AdminOverview, DailyCount


async def get_overview(db: AsyncSession) -> AdminOverview:
    today = date.today()
    today_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)

    total_users, new_users_today = await _count_with_today(db, User, User.created_at, today_start)
    total_sessions, new_sessions_today = await _count_with_today(db, ChatSession, ChatSession.created_at, today_start)
    total_messages, new_messages_today = await _count_with_today(db, ChatMessage, ChatMessage.created_at, today_start)

    pending_suggestions = (await db.execute(
        select(func.count()).select_from(SourceSuggestion).where(SourceSuggestion.status == "pending")
    )).scalar_one()

    pending_annotations = (await db.execute(
        select(func.count()).select_from(Annotation).where(Annotation.status == "pending")
    )).scalar_one()

    return AdminOverview(
        total_users=total_users,
        new_users_today=new_users_today,
        total_sessions=total_sessions,
        new_sessions_today=new_sessions_today,
        total_messages=total_messages,
        new_messages_today=new_messages_today,
        pending_suggestions=pending_suggestions,
        pending_annotations=pending_annotations,
    )


async def _count_with_today(db: AsyncSession, model, created_field, today_start: datetime):
    result = await db.execute(
        select(
            func.count(),
            func.count(case((created_field >= today_start, 1))),
        ).select_from(model)
    )
    row = result.one()
    return row[0], row[1]


async def get_trends(db: AsyncSession, days: int = 30) -> dict:
    since = date.today() - timedelta(days=days - 1)
    since_dt = datetime(since.year, since.month, since.day, tzinfo=timezone.utc)

    registrations = await _daily_counts(db, User, User.created_at, since_dt)
    messages = await _daily_counts(db, ChatMessage, ChatMessage.created_at, since_dt)
    active_users = await _daily_active_users(db, since_dt)

    return {
        "registrations": registrations,
        "messages": messages,
        "active_users": active_users,
    }


async def _daily_counts(db: AsyncSession, model, created_field, since: datetime) -> list[DailyCount]:
    day_col = cast(created_field, Date)
    result = await db.execute(
        select(day_col, func.count())
        .select_from(model)
        .where(created_field >= since)
        .group_by(day_col)
        .order_by(day_col)
    )
    return [DailyCount(date=str(row[0]), count=row[1]) for row in result.all()]


async def _daily_active_users(db: AsyncSession, since: datetime) -> list[DailyCount]:
    """Active users = distinct users who sent chat messages OR read texts each day."""
    chat_day = cast(ChatSession.created_at, Date)
    read_day = cast(ReadingHistory.last_read_at, Date)

    chat_q = (
        select(chat_day.label("day"), ChatSession.user_id.label("uid"))
        .where(ChatSession.created_at >= since, ChatSession.user_id.is_not(None))
    )
    read_q = (
        select(read_day.label("day"), ReadingHistory.user_id.label("uid"))
        .where(ReadingHistory.last_read_at >= since)
    )
    union_q = chat_q.union_all(read_q).subquery()

    result = await db.execute(
        select(union_q.c.day, func.count(distinct(union_q.c.uid)))
        .group_by(union_q.c.day)
        .order_by(union_q.c.day)
    )
    return [DailyCount(date=str(row[0]), count=row[1]) for row in result.all()]


async def list_users(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    q: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[int, list]:
    query = select(User)
    count_query = select(func.count()).select_from(User)

    if q:
        pattern = f"%{q}%"
        condition = User.username.ilike(pattern) | User.email.ilike(pattern)
        query = query.where(condition)
        count_query = count_query.where(condition)

    total = (await db.execute(count_query)).scalar_one()

    sort_col = getattr(User, sort_by, User.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_col.asc().nullslast())
    else:
        query = query.order_by(sort_col.desc().nullsfirst())

    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    return total, list(result.scalars().all())


async def list_annotations_for_review(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    status: str | None = None,
) -> tuple[int, list[AdminAnnotationItem]]:
    base = select(Annotation, User.username).join(User, Annotation.user_id == User.id)
    count_base = select(func.count()).select_from(Annotation)

    if status:
        base = base.where(Annotation.status == status)
        count_base = count_base.where(Annotation.status == status)

    total = (await db.execute(count_base)).scalar_one()

    query = base.order_by(Annotation.created_at.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(query)

    items = []
    for ann, username in result.all():
        items.append(AdminAnnotationItem(
            id=ann.id,
            text_id=ann.text_id,
            juan_num=ann.juan_num,
            annotation_type=ann.annotation_type,
            content=ann.content[:200],
            user_id=ann.user_id,
            username=username,
            status=ann.status,
            created_at=ann.created_at,
        ))
    return total, items
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/admin_service.py
git commit -m "feat(admin): add admin service with stats and user query logic"
```

---

## Task 4: Backend — Admin API Router

**Files:**
- Create: `backend/app/api/admin.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create admin API router**

Create `backend/app/api/admin.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.role_guard import require_role
from app.database import get_db
from app.models.user import User
from app.schemas.admin import (
    AdminAnnotationListResponse,
    AdminOverview,
    AdminTrends,
    AdminUserItem,
    AdminUserListResponse,
    AdminUserUpdate,
)
from app.services.admin_service import get_overview, get_trends, list_annotations_for_review, list_users

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats/overview", response_model=AdminOverview)
async def stats_overview(
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    return await get_overview(db)


@router.get("/stats/trends", response_model=AdminTrends)
async def stats_trends(
    days: int = Query(30, ge=1, le=365),
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    return AdminTrends(**(await get_trends(db, days)))


@router.get("/users", response_model=AdminUserListResponse)
async def user_list(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None),
    sort_by: str = Query("created_at", pattern="^(created_at|last_active_at)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    total, items = await list_users(db, page, size, q, sort_by, sort_order)
    return {"total": total, "page": page, "size": size, "items": items}


@router.patch("/users/{user_id}", response_model=AdminUserItem)
async def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能修改自己的角色或状态",
        )

    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/annotations", response_model=AdminAnnotationListResponse)
async def annotation_list(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    total, items = await list_annotations_for_review(db, page, size, status)
    return {"total": total, "page": page, "size": size, "items": items}
```

- [ ] **Step 2: Register admin router in main.py**

In `backend/app/main.py`, add the import (after existing imports around line 42):

```python
from app.api import (
    admin,
    annotations,
    ...
)
```

And register the router (after source_suggestions router, around line 161):

```python
# Admin dashboard
app.include_router(admin.router, prefix="/api")
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/admin.py backend/app/main.py
git commit -m "feat(admin): add admin API router with stats, users, and annotations endpoints"
```

---

## Task 5: Backend — LastActive Middleware

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add LastActiveMiddleware to main.py**

Add after the `RequestLoggingMiddleware` class definition (around line 111) in `backend/app/main.py`:

```python
class LastActiveMiddleware(BaseHTTPMiddleware):
    """Update user.last_active_at with 5-minute throttle."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Only update for authenticated API requests
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer ") or not request.url.path.startswith("/api/"):
            return response

        try:
            from app.core.auth import verify_token
            token = auth_header[7:]
            user_id = verify_token(token)
            if user_id is None:
                return response

            redis_client = getattr(request.app.state, "redis", None)
            if redis_client is None:
                return response

            # 5-minute throttle via Redis
            key = f"last_active:{user_id}"
            if await redis_client.set(key, "1", nx=True, ex=300):
                from app.database import async_session
                from app.models.user import User
                from sqlalchemy import update
                from datetime import datetime, timezone

                async with async_session() as session:
                    await session.execute(
                        update(User)
                        .where(User.id == user_id)
                        .values(last_active_at=datetime.now(timezone.utc))
                    )
                    await session.commit()
        except Exception:
            pass  # Never break request flow for activity tracking

        return response
```

Register it after `RequestLoggingMiddleware`:

```python
app.add_middleware(LastActiveMiddleware)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(admin): add LastActiveMiddleware with 5-minute Redis throttle"
```

---

## Task 6: Backend — Admin Tests

**Files:**
- Create: `backend/tests/test_admin.py`

- [ ] **Step 1: Write admin API tests**

Create `backend/tests/test_admin.py`:

```python
"""Admin API tests — stats, user management, annotations."""

from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _fake_user(uid=1, username="admin", role="admin", is_active=True):
    u = MagicMock()
    u.id = uid
    u.username = username
    u.email = f"{username}@example.com"
    u.display_name = username
    u.role = role
    u.is_active = is_active
    u.created_at = datetime.now(timezone.utc)
    u.updated_at = datetime.now(timezone.utc)
    u.last_active_at = datetime.now(timezone.utc)
    return u


@pytest.mark.anyio
async def test_stats_overview_requires_admin(client):
    """GET /admin/stats/overview without auth returns 401."""
    resp = await client.get("/api/admin/stats/overview")
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_stats_overview_non_admin(client):
    """GET /admin/stats/overview as regular user returns 403."""
    fake_user = _fake_user(role="user")
    from app.main import app
    from app.core.deps import get_current_user
    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        resp = await client.get("/api/admin/stats/overview")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_users_list_requires_admin(client):
    """GET /admin/users without auth returns 401."""
    resp = await client.get("/api/admin/users")
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_user_update_cannot_self_modify(client):
    """PATCH /admin/users/{self_id} should return 400."""
    fake_admin = _fake_user(uid=1, role="admin")
    from app.main import app
    from app.core.deps import get_current_user
    from app.database import get_db as real_get_db

    mock_db = AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: fake_admin
    app.dependency_overrides[real_get_db] = lambda: mock_db
    try:
        resp = await client.patch("/api/admin/users/1", json={"role": "user"})
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(real_get_db, None)


@pytest.mark.anyio
async def test_annotations_list_requires_admin(client):
    """GET /admin/annotations without auth returns 401."""
    resp = await client.get("/api/admin/annotations")
    assert resp.status_code in (401, 403)
```

- [ ] **Step 2: Run tests**

```bash
cd backend && python -m pytest tests/test_admin.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 3: Run full test suite**

```bash
cd backend && python -m pytest tests/ -q
```

Expected: All existing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_admin.py
git commit -m "test(admin): add admin API endpoint tests"
```

---

## Task 7: Frontend — Admin API Client

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add admin types and API methods**

Append to `frontend/src/api/client.ts` (after the existing source suggestion functions, before the Chat section):

```typescript
// --- Admin Dashboard ---

export interface AdminOverview {
  total_users: number;
  new_users_today: number;
  total_sessions: number;
  new_sessions_today: number;
  total_messages: number;
  new_messages_today: number;
  pending_suggestions: number;
  pending_annotations: number;
}

export interface DailyCount {
  date: string;
  count: number;
}

export interface AdminTrends {
  registrations: DailyCount[];
  messages: DailyCount[];
  active_users: DailyCount[];
}

export interface AdminUserItem {
  id: number;
  username: string;
  display_name: string | null;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
  last_active_at: string | null;
}

export interface AdminAnnotationItem {
  id: number;
  text_id: number;
  juan_num: number;
  annotation_type: string;
  content: string;
  user_id: number;
  username: string;
  status: string;
  created_at: string;
}

export async function getAdminOverview(): Promise<AdminOverview> {
  const { data } = await api.get<AdminOverview>("/admin/stats/overview");
  return data;
}

export async function getAdminTrends(days: number = 30): Promise<AdminTrends> {
  const { data } = await api.get<AdminTrends>("/admin/stats/trends", { params: { days } });
  return data;
}

export async function getAdminUsers(params: {
  page?: number;
  size?: number;
  q?: string;
  sort_by?: string;
  sort_order?: string;
}): Promise<PaginatedResponse<AdminUserItem>> {
  const { data } = await api.get<PaginatedResponse<AdminUserItem>>("/admin/users", { params });
  return data;
}

export async function updateAdminUser(
  id: number,
  payload: { role?: string; is_active?: boolean },
): Promise<AdminUserItem> {
  const { data } = await api.patch<AdminUserItem>(`/admin/users/${id}`, payload);
  return data;
}

export async function getAdminAnnotations(params: {
  page?: number;
  size?: number;
  status?: string;
}): Promise<PaginatedResponse<AdminAnnotationItem>> {
  const { data } = await api.get<PaginatedResponse<AdminAnnotationItem>>("/admin/annotations", { params });
  return data;
}
```

- [ ] **Step 2: Commit**

```bash
cd frontend && git add src/api/client.ts
git commit -m "feat(admin): add admin API client methods and types"
```

---

## Task 8: Frontend — AdminDashboardPage

**Files:**
- Create: `frontend/src/pages/AdminDashboardPage.tsx`

- [ ] **Step 1: Create AdminDashboardPage**

Create `frontend/src/pages/AdminDashboardPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Card, Col, Row, Statistic, Spin, message } from "antd";
import {
  UserOutlined,
  MessageOutlined,
  CommentOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { Helmet } from "react-helmet-async";
import { Line } from "@ant-design/charts";
import {
  getAdminOverview,
  getAdminTrends,
  type AdminOverview,
  type AdminTrends,
} from "../api/client";

export default function AdminDashboardPage() {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [trends, setTrends] = useState<AdminTrends | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getAdminOverview(), getAdminTrends(30)])
      .then(([ov, tr]) => {
        setOverview(ov);
        setTrends(tr);
      })
      .catch(() => message.error("加载统计数据失败"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!overview || !trends) return null;

  const chartData = [
    ...trends.registrations.map((d) => ({ ...d, type: "新注册" })),
    ...trends.messages.map((d) => ({ ...d, type: "消息数" })),
    ...trends.active_users.map((d) => ({ ...d, type: "活跃用户" })),
  ];

  const lineConfig = {
    data: chartData,
    xField: "date",
    yField: "count",
    colorField: "type",
    smooth: true,
    height: 360,
    axis: {
      x: { labelAutoRotate: false },
    },
  };

  return (
    <>
      <Helmet>
        <title>管理后台 - 佛津</title>
      </Helmet>
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        <Row gutter={[16, 16]}>
          <Col xs={12} sm={6}>
            <Card>
              <Statistic
                title="总用户数"
                value={overview.total_users}
                prefix={<UserOutlined />}
                suffix={<span style={{ fontSize: 13, color: "#52c41a" }}>+{overview.new_users_today}</span>}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card>
              <Statistic
                title="聊天会话"
                value={overview.total_sessions}
                prefix={<CommentOutlined />}
                suffix={<span style={{ fontSize: 13, color: "#52c41a" }}>+{overview.new_sessions_today}</span>}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card>
              <Statistic
                title="总消息数"
                value={overview.total_messages}
                prefix={<MessageOutlined />}
                suffix={<span style={{ fontSize: 13, color: "#52c41a" }}>+{overview.new_messages_today}</span>}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card>
              <Statistic
                title="待审核"
                value={overview.pending_suggestions + overview.pending_annotations}
                prefix={<WarningOutlined />}
                valueStyle={{ color: overview.pending_suggestions + overview.pending_annotations > 0 ? "#faad14" : undefined }}
              />
            </Card>
          </Col>
        </Row>

        <Card title="最近 30 天趋势" style={{ marginTop: 16 }}>
          <Line {...lineConfig} />
        </Card>
      </div>
    </>
  );
}
```

- [ ] **Step 2: Install @ant-design/charts**

```bash
cd frontend && npm install @ant-design/charts
```

- [ ] **Step 3: Commit**

```bash
cd frontend && git add src/pages/AdminDashboardPage.tsx package.json package-lock.json
git commit -m "feat(admin): add dashboard overview page with stats cards and trend charts"
```

---

## Task 9: Frontend — AdminUsersPage

**Files:**
- Create: `frontend/src/pages/AdminUsersPage.tsx`

- [ ] **Step 1: Create AdminUsersPage**

Create `frontend/src/pages/AdminUsersPage.tsx`:

```tsx
import { useEffect, useState, useCallback } from "react";
import { Table, Tag, Input, Select, Space, Typography, message, Popconfirm, Switch } from "antd";
import { SearchOutlined } from "@ant-design/icons";
import { Helmet } from "react-helmet-async";
import {
  getAdminUsers,
  updateAdminUser,
  type AdminUserItem,
} from "../api/client";
import { useAuthStore } from "../stores/authStore";

const roleColorMap: Record<string, string> = {
  admin: "red",
  reviewer: "blue",
  user: "default",
};

export default function AdminUsersPage() {
  const currentUser = useAuthStore((s) => s.user);
  const [items, setItems] = useState<AdminUserItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortOrder, setSortOrder] = useState("desc");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getAdminUsers({
        page,
        size: 20,
        q: search || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch {
      message.error("加载用户列表失败");
    } finally {
      setLoading(false);
    }
  }, [page, search, sortBy, sortOrder]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleToggleActive = async (record: AdminUserItem) => {
    try {
      await updateAdminUser(record.id, { is_active: !record.is_active });
      message.success(record.is_active ? "已禁用" : "已启用");
      fetchData();
    } catch {
      message.error("操作失败");
    }
  };

  const handleRoleChange = async (record: AdminUserItem, role: string) => {
    try {
      await updateAdminUser(record.id, { role });
      message.success("角色已更新");
      fetchData();
    } catch {
      message.error("操作失败");
    }
  };

  const columns = [
    {
      title: "用户名",
      dataIndex: "username",
      width: 120,
    },
    {
      title: "显示名",
      dataIndex: "display_name",
      width: 120,
      render: (v: string | null) => v || "-",
    },
    {
      title: "邮箱",
      dataIndex: "email",
      ellipsis: true,
    },
    {
      title: "角色",
      dataIndex: "role",
      width: 120,
      render: (role: string, record: AdminUserItem) => {
        if (record.id === currentUser?.id) {
          return <Tag color={roleColorMap[role]}>{role}</Tag>;
        }
        return (
          <Select
            size="small"
            value={role}
            style={{ width: 100 }}
            onChange={(v) => handleRoleChange(record, v)}
            options={[
              { value: "user", label: "user" },
              { value: "reviewer", label: "reviewer" },
              { value: "admin", label: "admin" },
            ]}
          />
        );
      },
    },
    {
      title: "状态",
      dataIndex: "is_active",
      width: 80,
      render: (active: boolean, record: AdminUserItem) => {
        if (record.id === currentUser?.id) {
          return <Tag color="green">正常</Tag>;
        }
        return (
          <Popconfirm
            title={active ? "确定禁用此用户？" : "确定启用此用户？"}
            onConfirm={() => handleToggleActive(record)}
            okText="确定"
            cancelText="取消"
          >
            <Switch checked={active} size="small" />
          </Popconfirm>
        );
      },
    },
    {
      title: "注册时间",
      dataIndex: "created_at",
      width: 170,
      sorter: true,
      render: (t: string) => new Date(t).toLocaleString("zh-CN"),
    },
    {
      title: "最后活跃",
      dataIndex: "last_active_at",
      width: 170,
      sorter: true,
      render: (t: string | null) => (t ? new Date(t).toLocaleString("zh-CN") : "-"),
    },
  ];

  return (
    <>
      <Helmet>
        <title>用户管理 - 佛津</title>
      </Helmet>
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        <Space style={{ marginBottom: 16, justifyContent: "space-between", width: "100%" }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            用户管理
          </Typography.Title>
          <Input.Search
            placeholder="搜索用户名或邮箱"
            allowClear
            prefix={<SearchOutlined />}
            style={{ width: 280 }}
            onSearch={(v) => {
              setSearch(v);
              setPage(1);
            }}
          />
        </Space>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={items}
          loading={loading}
          onChange={(_pagination, _filters, sorter) => {
            if (!Array.isArray(sorter) && sorter.field) {
              setSortBy(sorter.field as string);
              setSortOrder(sorter.order === "ascend" ? "asc" : "desc");
            }
          }}
          pagination={{
            current: page,
            total,
            pageSize: 20,
            onChange: setPage,
            showTotal: (t) => `共 ${t} 个用户`,
          }}
          size="middle"
        />
      </div>
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd frontend && git add src/pages/AdminUsersPage.tsx
git commit -m "feat(admin): add user management page with search, role change, and toggle active"
```

---

## Task 10: Frontend — AdminAnnotationsPage

**Files:**
- Create: `frontend/src/pages/AdminAnnotationsPage.tsx`

- [ ] **Step 1: Create AdminAnnotationsPage**

Create `frontend/src/pages/AdminAnnotationsPage.tsx`:

```tsx
import { useEffect, useState, useCallback } from "react";
import { Table, Tag, Button, Space, Select, Typography, message } from "antd";
import { CheckOutlined, CloseOutlined } from "@ant-design/icons";
import { Helmet } from "react-helmet-async";
import { getAdminAnnotations, type AdminAnnotationItem } from "../api/client";
import { reviewAnnotation } from "../api/client";

const statusColorMap: Record<string, string> = {
  draft: "default",
  pending: "orange",
  approved: "green",
  rejected: "red",
};

const statusLabelMap: Record<string, string> = {
  draft: "草稿",
  pending: "待审核",
  approved: "已通过",
  rejected: "已拒绝",
};

const typeLabel: Record<string, string> = {
  note: "笔记",
  correction: "勘误",
  tag: "标签",
};

export default function AdminAnnotationsPage() {
  const [items, setItems] = useState<AdminAnnotationItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>("pending");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getAdminAnnotations({
        page,
        size: 20,
        status: statusFilter,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch {
      message.error("加载标注列表失败");
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleReview = async (id: number, action: string) => {
    try {
      await reviewAnnotation(id, { action });
      message.success(action === "approve" ? "已通过" : "已拒绝");
      fetchData();
    } catch {
      message.error("操作失败");
    }
  };

  const columns = [
    {
      title: "类型",
      dataIndex: "annotation_type",
      width: 80,
      render: (t: string) => typeLabel[t] || t,
    },
    {
      title: "内容",
      dataIndex: "content",
      ellipsis: true,
    },
    {
      title: "用户",
      dataIndex: "username",
      width: 120,
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (s: string) => <Tag color={statusColorMap[s]}>{statusLabelMap[s] || s}</Tag>,
    },
    {
      title: "提交时间",
      dataIndex: "created_at",
      width: 170,
      render: (t: string) => new Date(t).toLocaleString("zh-CN"),
    },
    {
      title: "操作",
      width: 180,
      render: (_: unknown, record: AdminAnnotationItem) =>
        record.status === "pending" ? (
          <Space>
            <Button
              type="primary"
              size="small"
              icon={<CheckOutlined />}
              onClick={() => handleReview(record.id, "approve")}
            >
              通过
            </Button>
            <Button
              danger
              size="small"
              icon={<CloseOutlined />}
              onClick={() => handleReview(record.id, "reject")}
            >
              拒绝
            </Button>
          </Space>
        ) : null,
    },
  ];

  return (
    <>
      <Helmet>
        <title>标注审核 - 佛津</title>
      </Helmet>
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        <Space style={{ marginBottom: 16, justifyContent: "space-between", width: "100%" }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            标注审核
          </Typography.Title>
          <Select
            style={{ width: 140 }}
            placeholder="筛选状态"
            allowClear
            value={statusFilter}
            onChange={(v) => {
              setStatusFilter(v);
              setPage(1);
            }}
            options={[
              { value: "pending", label: "待审核" },
              { value: "approved", label: "已通过" },
              { value: "rejected", label: "已拒绝" },
              { value: "draft", label: "草稿" },
            ]}
          />
        </Space>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={items}
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 20,
            onChange: setPage,
            showTotal: (t) => `共 ${t} 条`,
          }}
          size="middle"
        />
      </div>
    </>
  );
}
```

- [ ] **Step 2: Verify `reviewAnnotation` is exported from client.ts**

Check if `reviewAnnotation` exists in `frontend/src/api/client.ts`. If not, add:

```typescript
export async function reviewAnnotation(
  annotationId: number,
  payload: { action: string; comment?: string },
): Promise<void> {
  await api.post(`/annotations/${annotationId}/review`, payload);
}
```

- [ ] **Step 3: Commit**

```bash
cd frontend && git add src/pages/AdminAnnotationsPage.tsx src/api/client.ts
git commit -m "feat(admin): add annotation review management page"
```

---

## Task 11: Frontend — Routing and Navigation

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout.tsx`
- Modify: `frontend/public/locales/zh/translation.json`
- Modify: `frontend/public/locales/en/translation.json`

- [ ] **Step 1: Add lazy imports and routes in App.tsx**

In `frontend/src/App.tsx`, add lazy imports (after line 31):

```typescript
const AdminDashboardPage = lazy(() => import("./pages/AdminDashboardPage"));
const AdminUsersPage = lazy(() => import("./pages/AdminUsersPage"));
const AdminAnnotationsPage = lazy(() => import("./pages/AdminAnnotationsPage"));
```

Replace the existing admin route block (lines 66-68):

```tsx
<Route element={<ProtectedRoute requiredRole="admin" />}>
  <Route path="/admin" element={<AdminDashboardPage />} />
  <Route path="/admin/users" element={<AdminUsersPage />} />
  <Route path="/admin/suggestions" element={<AdminSuggestionsPage />} />
  <Route path="/admin/annotations" element={<AdminAnnotationsPage />} />
</Route>
```

- [ ] **Step 2: Update Layout.tsx navigation**

In `frontend/src/components/Layout.tsx`, replace the admin nav item (lines 70-78) with a sub-menu structure.

Add imports at top:

```typescript
import {
  DashboardOutlined,
} from "@ant-design/icons";
```

Replace the admin navItems section:

```typescript
...(isAdmin
  ? [
      {
        icon: <Badge count={pendingCount} size="small" offset={[4, -2]}><DashboardOutlined /></Badge>,
        label: t("nav.admin"),
        path: "/admin",
        children: [
          { label: t("nav.admin_overview"), path: "/admin" },
          { label: t("nav.admin_users"), path: "/admin/users" },
          { label: t("nav.admin_suggestions"), path: "/admin/suggestions" },
          { label: t("nav.admin_annotations"), path: "/admin/annotations" },
        ],
      },
    ]
  : []),
```

Update the nav rendering to support dropdown children. For the desktop nav, wrap admin items with Dropdown:

```tsx
{navItems.map((item) =>
  item.children ? (
    <Dropdown
      key={item.path}
      menu={{
        items: item.children.map((child) => ({
          key: child.path,
          label: child.label,
          onClick: () => navigate(child.path),
        })),
      }}
    >
      <Button
        type="text"
        icon={item.icon}
        style={{ color: inkMuted, fontSize: 13, fontWeight: 400, fontFamily: '"Noto Serif SC", serif' }}
      >
        {item.label}
      </Button>
    </Dropdown>
  ) : (
    <Button
      key={item.path}
      type="text"
      icon={item.icon}
      style={{ color: inkMuted, fontSize: 13, fontWeight: 400, fontFamily: '"Noto Serif SC", serif' }}
      onClick={() => navigate(item.path)}
    >
      {item.label}
    </Button>
  ),
)}
```

Similarly update the Drawer mobile nav to show admin sub-items inline.

- [ ] **Step 3: Add i18n labels**

In `frontend/public/locales/zh/translation.json`, add:

```json
"nav.admin_overview": "数据概览",
"nav.admin_users": "用户管理",
"nav.admin_suggestions": "源建议",
"nav.admin_annotations": "标注审核",
```

In `frontend/public/locales/en/translation.json`, add:

```json
"nav.admin_overview": "Overview",
"nav.admin_users": "Users",
"nav.admin_suggestions": "Suggestions",
"nav.admin_annotations": "Annotations",
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/Layout.tsx frontend/public/locales/zh/translation.json frontend/public/locales/en/translation.json
git commit -m "feat(admin): add admin routes and sub-menu navigation"
```

---

## Task 12: Lint and Type Check

**Files:** All modified files

- [ ] **Step 1: Backend lint**

```bash
cd backend && ruff check app/
```

Expected: No errors. Fix any issues.

- [ ] **Step 2: Frontend lint and type check**

```bash
cd frontend && npx eslint src/ && npx tsc -b --noEmit
```

Expected: 0 errors. Fix any issues.

- [ ] **Step 3: Run all backend tests**

```bash
cd backend && python -m pytest tests/ -q
```

Expected: All tests pass.

- [ ] **Step 4: Fix any issues found and commit**

If fixes needed:

```bash
git add -A && git commit -m "fix(admin): lint and type check fixes"
```
