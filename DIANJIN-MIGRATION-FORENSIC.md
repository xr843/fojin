# Dianjin Untracked Migration 考古报告

**调查时间**：2026-05-08
**调查人**：Claude Opus 4.7（只读模式）
**主机**：sg-vps (100.67.232.7) — `/home/admin/fojin`
**核心结论（一句话）**：**所有 54 个 dianjin sources 已 100% 落库**，3 个 untracked 文件是**有意 gitignored 的私有 dianjin 模块本地副本**，不是流程 bug；唯一真正的 bug 是 commit `e582a5e` (PR #542) 把这些文件**重命名到 0130/0131/0132**但 sg-vps 上的旧文件没同步重命名 → 旧 0027/0032/0035 残留 → backend 启动时 alembic 看到两个 head（0129 公链 + 0035 旧 dianjin 链）。

---

## 1. 数据落库情况

| 指标 | 值 |
|---|---|
| `alembic_version.version_num` | **0129**（master 当前 head）|
| `data_sources` 总条数 | 636 |
| 0027 中 14 个 codes 在 DB | **14 / 14 ✅** |
| 0032 中 33 个 codes 在 DB | **33 / 33 ✅** |
| 0035 中 7 个新 codes 在 DB | **7 / 7 ✅** |
| **dianjin 数据落库率** | **54 / 54 = 100%** |

**核实方式**：在 `fojin-postgres` 容器内 `SELECT code FROM data_sources WHERE code IN (...)`，对比每个 migration `SOURCES` 列表里的 `code` 字段，全部命中（`dianjin / shidianguji / cadal / hathitrust / nl-korea / ... / hannom-heritage / taipei-npm-guji / hdcg-wenyuan` 等 54 项均存在）。

**结论**：3 个 migration 在过去某个时间点（≥ 2026-03-05）已经在生产 DB 完整运行过。`alembic_version` 现在停留在 0129 而不是带 dianjin 编号——这是因为公链已经被人为重排（见 §2-§3）。

---

## 2. 文件冲突情况

git 历史里**完全不存在** revision 0027/0032/0035 的文件。master 上从 0026 直接跳到 0028，0031 跳到 0033，0034 跳到 0036。

| revision | git tracked 版本 | sg-vps untracked 版本 | 冲突类型 |
|---|---|---|---|
| 0027 | **不存在**（master 跳过此号）| `0027_seed_dianjin_sources.py` (Mar 2 mtime, 14 sources) | 链断 + 0028 down_revision 已被改为 0026 |
| 0032 | **不存在** | `0032_import_dianjin_datasources.py` (Mar 5 mtime, 33 sources) | 链断 + 0033 down_revision 已被改为 0031 |
| 0035 | **不存在** | `0035_supplement_dianjin_cross_reference.py` (Mar 3 mtime, 7 new + 6 update) | 链断 + 0036 down_revision 已被改为 0034 |

**关键 commit**：`e582a5e fix(alembic): repair migration chain after DianJin removal`（2026-05-08 12:49，PR #542 merged 12:56）。该 commit 把 0028/0033/0036 的 `down_revision` 从 0027/0032/0035 改成 0026/0031/0034，并在 `.gitignore` 里把三份本地 dianjin 文件**重命名**到 0130/0131/0132（接在当前 head 0129 后面，避免再撞公链）。

**冲突机制**（部署 PR #544 时 backend crash loop 的 root cause）：
- master pull 下来后，`0028.down_revision = 0026`、`0033 = 0031`、`0036 = 0034`；
- 但 sg-vps 文件系统上**老的** `0027_seed_dianjin_sources.py` 等 3 个文件还在，且仍声明 `revision = "0027"`、是 0028 的 parent；
- `alembic upgrade head` 扫描 versions/ 目录，看到 0027 这个孤儿 revision（指向 0026），**同时** 0028 也指向 0026 → 出现两条从 0026 出发的分支 → multiple heads → backend 报错退出 → crash loop。

把 3 个文件移走之后，链回到单 head 0129，backend 起来。**一切对上了。**

---

## 3. 流程 bug 假设

**这不是"在 prod 直接放未 commit migration"的 bug。** 真相：

- DianJin（典津）是用户**有意保留为私有**的本地 dev 模块（`backend/app/api/dianjin.py` 等十多个文件全部在 `.gitignore`）。原 `.gitignore` 把 migration 也按 `0027/0032/0035` 编号忽略掉，本意是允许本地 dev 跑这套 migration 但不进开源 repo。
- 文件 ownership=`admin admin`，mtime 与 commit `9bdf4d1` (2026-03-21 `feat(backend): add rollback on RAG error + env vars for embedding/dianjin`) 等附近私有 commit 时间一致 → 这些是用户 ~3 月份在 sg-vps 上手工放置 / scp 上来跑的，跑成功后数据进 DB，alembic_version 当时应当是 0035（或更高，但已被后续 master 反复 upgrade 过）。
- 真正的设计漏洞：**老方案让私有 migration 占用 0027/0032/0035 这种"低号、贴在公链中段"的位置**，导致一旦未来公链编号继续往上走或公链结构调整，私有 migration 就会和公链冲突（而本次 PR #542 正是为修复 CI 跑公链时的 KeyError）。
- PR #542 已经把这个设计改正：把 dianjin 私有 migration 重命名到 0130/0131/0132，**接在 head 后面**而不是嵌在中段。但 sg-vps 部署时**没有**手工执行配套的"重命名旧文件 + 改 revision/down_revision 字符串"操作，所以老文件继续躺在那里。

参考 `feedback_fojin_add_source_pattern.md` 提示"加 data source 走 alembic migration（不走 admin UI）"——dianjin 模块就是这种 gitignored migration 流程的极端案例。

**memory 里没有遗漏；本次只是 #542 的部署后置步骤未做。**

---

## 4. 处置建议

数据**已全部落库**，走方案 A。

### 方案 A：已落库（推荐）

1. **保留** `/tmp/fojin-untracked-migrations-20260508/` 下的 3 个文件至少 7 天（取证 + 万一回滚）。
2. **重命名 + 改写 revision 字段**，按 #542 commit message 指示：
   ```
   0027_seed_dianjin_sources.py            → 0130_seed_dianjin_sources.py
       revision "0027" → "0130"，down_revision "0026" → "0129"
   0032_import_dianjin_datasources.py      → 0131_import_dianjin_datasources.py
       revision "0032" → "0131"，down_revision "0031" → "0130"
   0035_supplement_dianjin_cross_reference → 0132_supplement_dianjin_cross_reference.py
       revision "0035" → "0132"，down_revision "0034" → "0131"
   ```
3. 把改名后的 3 个文件放回 `/home/admin/fojin/backend/alembic/versions/`（仍然是 gitignored）。
4. 在 PG `alembic_version` 表里把 `version_num` 从 `0129` **手工 stamp 到 `0132`**（因为数据已落库，不能再让 0130/0131/0132 的 `upgrade()` 真去跑 INSERT，那样会触发 `code` UNIQUE 冲突——其实代码里有 SELECT 后 UPDATE/INSERT 分支，会安全 no-op，但更干净的是 stamp）：
   ```bash
   docker exec fojin-backend alembic stamp 0132
   ```
   或 SQL：`UPDATE alembic_version SET version_num = '0132';`
5. 重启 backend 验证 `alembic heads` 单 head=0132、HTTP /healthz OK。
6. **不要**把 SOURCES 重新跑一遍——0027/0032/0035 的 upgrade() 函数对已存在 code 走 UPDATE 分支，但 0035 的 UPDATES 会把 6 个已有 source 的 `description` 覆盖为预设值，可能回退掉已有的人工编辑。stamp 是安全选项。

### 方案 B：未落库（**不适用本次**——仅作为对照）

直接 `rm /tmp/fojin-untracked-migrations-20260508/*.py` 并删掉本地副本即可，alembic_version 已是 0129、master 公链干净。

---

## 5. 防御加固建议（不实施，仅建议）

在 `backend/entrypoint.sh` 或 alembic 启动包装里加预检：

```bash
# Pre-flight: alembic must have exactly one head
HEADS=$(alembic heads --resolve-dependencies 2>&1 | grep -c '(head)')
if [ "$HEADS" -ne 1 ]; then
    echo "FATAL: alembic has $HEADS heads, expected 1. Aborting." >&2
    alembic heads >&2
    echo "Likely cause: stale local migration files conflicting with master chain." >&2
    echo "Check backend/alembic/versions/ for files not in 'git ls-files'." >&2
    exit 1
fi
```

配套 CI 加一条 lint：扫描 `backend/alembic/versions/` 目录，要求每个 `.py` 的 `revision` 字段在合法的私有 reserved range（≥ 9000 或加专属前缀）或 `git ls-tree HEAD` 里——否则 fail。这样下次 dianjin 类私有 migration 用错号会在 PR 阶段就被拦下，而不是部署到 prod 才崩。

另外更轻量的：把 `.gitignore` 里 dianjin migration 的预期路径写到 `backend/alembic/README.md` + `CLAUDE.md`，部署 runbook 加一条"私有 migration 文件名 vs revision 字段必须配对"的 checklist。

---

## 附录 A：3 个 untracked migration 内容摘要

| File | Revision Chain | INSERT/UPDATE 行为 | DDL? | 敏感信息 |
|---|---|---|---|---|
| 0027_seed_dianjin_sources.py | 0027 → 0026 | 14 sources（dianjin/shidianguji/cadal/hathitrust + 10 个机构）；INSERT or UPDATE description+supports_* | 无 | 无 |
| 0032_import_dianjin_datasources.py | 0032 → 0031 | 33 sources（来自典津公开 API v1.1.76 抓的中日韩港澳法越机构数据库）；INSERT or skip | 无 | 无 |
| 0035_supplement_dianjin_cross_reference.py | 0035 → 0034 | 7 NEW_SOURCES + 6 UPDATES（覆盖已有 description）；INSERT or skip + UPDATE description | 无 | 无 |

无密码、token、API key 出现在文件内容中（已通读）。

## 附录 B：核心证据命令清单

```bash
# 1. 落库验证（54 / 54）
docker exec fojin-postgres psql -U fojin -d fojin -tAc \
  "SELECT code FROM data_sources WHERE code IN ('dianjin','shidianguji',...);"

# 2. alembic 当前位置
docker exec fojin-postgres psql -U fojin -d fojin -c \
  "SELECT version_num FROM alembic_version;"
# → 0129

# 3. 关键修复 commit
git log --all --oneline -S "DianJin removal"
# → e582a5e fix(alembic): repair migration chain after DianJin removal

# 4. .gitignore 配套
grep -A6 "DianJin" .gitignore
# → 看到 0130/0131/0132 期望路径
```
