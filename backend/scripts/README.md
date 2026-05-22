# backend/scripts/

数据管线与运维脚本。

## 目录约定

- **根目录** — 仍在使用的脚本：cron 周期任务、容器启动钩子、导入编排
  wrapper、共享库、可重复运行的诊断工具。
- **`archive/`** — 一次性脚本：已完成使命的数据导入 / 回填 / 清理脚本。
  保留作**历史参考 / 可复现文档**（记录数据是怎么建起来的），不再日常运行。
  按用途分子目录：`imports/ fetch/ backfill/ enrich/ cleanup/ seed/ misc/`。

> ⚠️ 归档脚本多数在文件头用 `dirname(__file__)` 按「自己位于 `scripts/` 下」
> 自举 `sys.path`，移入子目录后该路径不再成立 —— **不能原地直接运行**。
> 若灾备需重跑某个归档脚本，先 `git mv` 移回 `scripts/` 根目录再执行。

## 活跃脚本

### cron 周期任务（生产 crontab）

| 脚本 | 频率 | 用途 |
|---|---|---|
| `fetch_academic_feeds.py` | 每日 6:00 | 抓取学术 RSS |
| `sync_dila_combined.py` | 每日 3:30 | 同步 DILA 人物（RDF 批量 + API 增量） |
| `run_amap_v3.sh` | 每日 0:30 | 高德逆地理回填（V3 抓取已禁用，free quota 不足） |
| `backfill_address_regeo.py` | 每日 12:30 | 高德逆地理回填寺院地址 |
| `health_check_sources.py` | 每日 4:30 | 数据源可达性探测 |

### 容器启动

- `seed_hot_questions.py` — 由 `backend/entrypoint.sh` 调用（容错，失败不阻断启动）。

### 导入编排 wrapper

- `import_cbeta_full.sh` — CBETA 全量导入，依次调用 `import_catalog`、
  `import_content`、`backfill_cbeta_identifiers`、`import_cbeta_alt_translations`、
  `extract_structured_kg`、`import_stats`。
- `run_amap_v3.sh` — 当前仅调用 `backfill_address_regeo`；V3 抓取因免费 quota 卡死
  16 天（2026-05-23 确认）已禁用，`fetch_amap_temples_v3` + `import_amap_temples_v3`
  脚本保留供未来 quota 升级后重启。

### 共享库

- `base_importer.py` — `BaseImporter` 基类，约 28 个导入脚本继承。
- `import_dila_dict.py` — `DilaBaseImporter`，DILA 辞典导入脚本继承。

### 诊断工具（可重复运行）

- `audit_*.py`、`check_*.py`、`validate_*.py`、`show_data_sources.py`
