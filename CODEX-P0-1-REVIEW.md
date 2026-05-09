# Codex 独立复核：FoJin BYOK 加密弱点 (P0-1)

**复核日期**: 2026-05-08
**复核工具**: `codex exec` (OpenAI Codex CLI, ChatGPT Plus OAuth)
**主审**: Claude Opus 4.7 (1M ctx)
**目标文件**: `backend/app/core/crypto.py`

---

## 一句话结论

Codex **部分同意**主审：弱点应修，但**不是 P0 紧急加密失败，而是 P1 操作层面爆炸半径收敛**。推荐路径 **A（强制重加密，受控 migration）+ 单 PR + 无 per-user salt + 静默后端重加密**。

---

## Codex 的核心论点

1. **不是真正的密码学破绽**：JWT secret ≥32 char + SHA-256 派生 + Fernet（AES-128-CBC + HMAC）在威胁模型下不可被实际利用。Salt/HKDF 不是核心问题。
2. **真正的问题是 key separation**：同一 secret 同时承担 JWT 签名与 BYOK at-rest 加密 ⇒ JWT 泄露=API key 泄露；JWT rotation 会 brick 已加密 BYOK 行；日志/配置 dump 一处暴露双重语义。这才是值得修的 blast radius。
3. **路径 A（强制重加密）优于 B（lazy）**：100~10000 行体量小；保留 v1 decrypt 分支永久存在反而长期延续旧 blast radius，复杂度更高。但要做"受控 migration"——不是裸启动惊吓——需要 lock、备份指引、metrics、fail-fast。
4. **单 PR**：dedicated key + KDF 硬化是同一个版本跃迁（v2）的两个面，拆分会制造中间不一致状态，review 成本翻倍。
5. **不要 per-user salt**：Fernet 本身每次加密带 fresh nonce；HKDF salt 不能补偿"高熵随机源"的（不存在的）弱点。**最佳方案是直接 `Fernet.generate_key()` 作为 `API_KEY_ENCRYPTION_KEY`，不走 KDF**。若坚持 HKDF，用全局 `info="fojin-api-key-encryption-v2"`。
6. **静默后端重加密**：每行事务化 re-encrypt，**v2 成功前不覆盖 v1 ciphertext**，失败行仅记录不删除。强制用户重填只在确认密钥泄露场景下合理。

---

## 主审（我）对 Codex 回答的评估

| 论点 | 评估 | 备注 |
|---|---|---|
| 降级为 P1 | **采纳** | 主审最初定 P0 偏严。当前 JWT secret 来自 env 且 ≥32 char 校验，威胁模型主要是"secret reuse"操作风险，确实 P1 更准确。 |
| 路径 A 但要受控 | **采纳** | 主审原方案"启动时一次性 re-encrypt"过于激进，应改为可重入、有 lock、可观测的 management command 或显式 startup migration。 |
| 单 PR | **采纳** | 主审原意也是单 PR，无分歧。 |
| 直接用 `Fernet.generate_key()` 跳过 HKDF | **采纳** | 比主审"HKDF + salt"更简洁。HKDF 是为低熵源设计；32 字节随机字节不需要二次派生。 |
| 不要 per-user salt | **采纳** | 主审原方案隐含 global salt，无分歧。 |
| 静默后端重加密 | **有保留** | 同意默认走静默路径，但建议保留"用户主动 rotate key"的入口（不是强制），并对 v1→v2 失败行**邮件/admin 通知**而非纯日志。 |

主要采纳点：**降级 P1、单 PR、直接生成 Fernet key、保留旧 ciphertext fallback**。

---

## 给用户的下一步建议

1. **单一 PR**，标题建议 `feat(crypto): split BYOK encryption key from JWT secret (v2)`
2. 改动范围：
   - `config.py` 新增 `API_KEY_ENCRYPTION_KEY` env（启动校验为合法 Fernet key），缺失时**production 拒启**、dev fallback 到 JWT secret 并打 WARN
   - `crypto.py` 增加 `kdf_version` 解析；v1 走旧逻辑，v2 走新 key
   - User 表 alembic migration 加 `api_key_kdf_version SMALLINT DEFAULT 1`
   - 新增 `manage.py migrate-api-keys` 命令：批量 v1→v2，事务化，**v2 写入成功后才更新 version 字段**，原 ciphertext 保留 30 天再 drop
3. **不要在启动 hook 里跑 migration**——改成显式命令 + 部署 runbook
4. 部署时序：deploy v2 代码（双读 v1+v2）→ 跑 migration → 观察 1 周 → 下个 release 删 v1 分支
5. 优先级标 **P1** 不是 P0；本周排期，不阻塞当前 chat input v2 冲刺

---

**Codex raw 输出**: `/tmp/codex-p01-raw.txt`
**Prompt**: `/tmp/codex-p01-prompt.md`
