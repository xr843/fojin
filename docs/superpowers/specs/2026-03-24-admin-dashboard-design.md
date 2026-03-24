# Admin Dashboard Design Spec

## Overview

为 FoJin 添加管理后台，提供数据概览、用户管理、源建议管理、标注审核四个模块。所有页面仅 admin 角色可访问。

## Pages

### 1. 数据概览 (`/admin`)

**指标卡片（顶部）：**

| 指标 | 数据来源 |
|------|---------|
| 总用户数 / 今日新增 | `users` 表 COUNT + WHERE created_at >= today |
| 总聊天会话数 / 今日新增 | `chat_sessions` 表 COUNT |
| 总消息数 / 今日新增 | `chat_messages` 表 COUNT |
| 待审核数 | source_suggestions(pending) + annotations(pending) |

**趋势图（最近 30 天）：**
- 用户注册趋势：按天 COUNT `users.created_at`
- AI 问答使用趋势：按天 COUNT `chat_messages.created_at`
- 活跃用户趋势：按天 COUNT DISTINCT `chat_sessions.user_id` UNION `reading_history.last_read_at`

图表库：`@ant-design/charts`（Line chart）

### 2. 用户管理 (`/admin/users`)

**表格列：**
- username, display_name, email, role, is_active, created_at, last_active_at

**操作：**
- 启用/禁用（toggle is_active）
- 角色调整（下拉选择 user/reviewer/admin）

**搜索：** 按 username 或 email 模糊搜索（ILIKE）

**排序：** created_at DESC（默认），支持 last_active_at 排序

**分页：** 20 条/页

### 3. 源建议管理 (`/admin/suggestions`)

已有 `AdminSuggestionsPage.tsx`，保持不变，纳入 admin 导航体系。

### 4. 标注审核 (`/admin/annotations`)

新建页面，展示待审核标注列表。

**表格列：** 标注类型、内容摘要、所属经文、提交用户、提交时间、操作
**操作：** 通过/拒绝（调用已有 `/annotations/{id}/review` API）

## Data Model Changes

### User 表新增字段

```sql
ALTER TABLE users ADD COLUMN last_active_at TIMESTAMP WITH TIME ZONE;
```

### 活跃时间更新机制

FastAPI 中间件，在每次认证请求成功后：
1. 检查 `user.last_active_at` 是否在 5 分钟内
2. 若超过 5 分钟或为 NULL，异步更新 `last_active_at = now()`
3. 节流避免频繁写库

## Backend API

所有端点前缀 `/api/admin/`，使用 `require_role("admin")` 保护。

### `GET /api/admin/stats/overview`

Response:
```json
{
  "total_users": 381,
  "new_users_today": 5,
  "total_sessions": 1200,
  "new_sessions_today": 30,
  "total_messages": 8500,
  "new_messages_today": 150,
  "pending_suggestions": 3,
  "pending_annotations": 7
}
```

缓存策略：Redis 缓存 5 分钟。

### `GET /api/admin/stats/trends?days=30`

Response:
```json
{
  "registrations": [{"date": "2026-03-01", "count": 5}, ...],
  "messages": [{"date": "2026-03-01", "count": 120}, ...],
  "active_users": [{"date": "2026-03-01", "count": 45}, ...]
}
```

缓存策略：Redis 缓存 30 分钟。

### `GET /api/admin/users?page=1&size=20&q=&sort_by=created_at&sort_order=desc`

Response: `PaginatedResponse<AdminUserItem>`

```json
{
  "total": 381,
  "page": 1,
  "size": 20,
  "items": [{
    "id": 1,
    "username": "贤任",
    "display_name": "贤任",
    "email": "...",
    "role": "admin",
    "is_active": true,
    "created_at": "2025-01-01T00:00:00Z",
    "last_active_at": "2026-03-24T10:00:00Z"
  }]
}
```

### `PATCH /api/admin/users/{id}`

Request body:
```json
{
  "role": "reviewer",    // optional
  "is_active": false     // optional
}
```

安全约束：不能修改自己的角色和状态（防止 admin 把自己锁住）。

### `GET /api/admin/annotations?page=1&size=20&status=pending`

Response: `PaginatedResponse<AnnotationReviewItem>`

复用已有 Annotation 模型，新增列表查询端点。

## Frontend Architecture

### 导航

Layout.tsx 中 admin 导航改为带子菜单：

```
管理后台（仅 admin 可见）
  ├── 数据概览
  ├── 用户管理
  ├── 源建议
  └── 标注审核
```

使用 Ant Design Menu 的 SubMenu 或 inline 展开。

### 路由

```tsx
<Route element={<ProtectedRoute requiredRole="admin" />}>
  <Route path="/admin" element={<AdminDashboardPage />} />
  <Route path="/admin/users" element={<AdminUsersPage />} />
  <Route path="/admin/suggestions" element={<AdminSuggestionsPage />} />
  <Route path="/admin/annotations" element={<AdminAnnotationsPage />} />
</Route>
```

### 新增前端文件

```
frontend/src/pages/
  AdminDashboardPage.tsx    — 数据概览（指标卡片 + 图表）
  AdminUsersPage.tsx        — 用户管理表格
  AdminAnnotationsPage.tsx  — 标注审核表格
```

### API Client 新增方法

```typescript
// admin stats
getAdminOverview(): Promise<AdminOverview>
getAdminTrends(days?: number): Promise<AdminTrends>

// admin users
getAdminUsers(params: AdminUserQuery): Promise<PaginatedResponse<AdminUserItem>>
updateAdminUser(id: number, data: AdminUserUpdate): Promise<void>

// admin annotations
getAdminAnnotations(params: AdminAnnotationQuery): Promise<PaginatedResponse<AnnotationReviewItem>>
```

## Security

- 所有 admin API 通过 `require_role("admin")` 保护
- 前端路由通过 `ProtectedRoute requiredRole="admin"` 保护
- admin 不能修改自己的 role/is_active
- 用户操作（禁用/角色变更）需二次确认（Ant Design Popconfirm）

## Not In Scope

- 搜索热词统计（当前无搜索日志，需另行实现日志记录）
- 系统监控（服务器资源、Docker 状态等）
- 操作审计日志
- 批量用户操作
