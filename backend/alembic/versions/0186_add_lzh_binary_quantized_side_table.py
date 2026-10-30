"""汉文嵌入的二值量化旁路表——中文检索臂被 HNSW 漏空时的兜底。

Revision ID: 0186
Revises: 0185
Create Date: 2026-10-30

HNSW 图对部分查询够不到汉文区域，再叠 ``bt.lang = 'lzh'`` 的后置过滤，中文检索臂就
返回 0 行（2026-09-22 实测：ef_search 提到 1000 也救不回来；iterative_scan 返回的是
差的那批且要 1.4–35 秒）。#1248 之后这类提问诚实地走无来源路径；精确扫描（关索引）
能找回真正的最近邻，可 42 万条 1024 维向量扫一遍要 19 秒。

这张表把每条汉文嵌入压成 1024 位（128 字节），42 万条约 71 MB，整表常驻内存：
按汉明距离精扫取 1000 条候选、再回主表按真余弦精排，中位 530 ms；35 道漏空首问上
首条与精确扫描 35/35 一致、前 5 重合 4.71/5。只在兜底时用，不替换 HNSW。上线依据：2026-10-28 配对评测，35 道漏空的
会话首问补上出处后有引文回答 6→26，逐字 90.9%、卷号 91.5%，所引经 23 道里对题 14 /
部分 6 / 不相关 3。

不改动 text_embeddings 与现有索引（给 11 GB 的主表加列回填会膨胀出等量写入，生产
磁盘放不下）。新增/重算的嵌入由触发器同步；删除随外键级联。没有 ORM 模型——它只
被 embedding.lzh_quantized_search 用原生 SQL 读。
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0186"
down_revision: str | None = "0185"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE text_embeddings_bq (
            id integer PRIMARY KEY REFERENCES text_embeddings(id) ON DELETE CASCADE,
            b bit(1024) NOT NULL
        )
        """
    )
    op.execute(
        """
        INSERT INTO text_embeddings_bq (id, b)
        SELECT te.id, binary_quantize(te.embedding)::bit(1024)
        FROM text_embeddings te JOIN buddhist_texts bt ON bt.id = te.text_id
        WHERE bt.lang = 'lzh' AND te.embedding IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE FUNCTION text_embeddings_bq_sync() RETURNS trigger AS $$
        BEGIN
            IF NEW.embedding IS NULL THEN
                DELETE FROM text_embeddings_bq WHERE id = NEW.id;
            ELSIF EXISTS (SELECT 1 FROM buddhist_texts WHERE id = NEW.text_id AND lang = 'lzh') THEN
                INSERT INTO text_embeddings_bq (id, b)
                VALUES (NEW.id, binary_quantize(NEW.embedding)::bit(1024))
                ON CONFLICT (id) DO UPDATE SET b = EXCLUDED.b;
            END IF;
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_text_embeddings_bq_sync
        AFTER INSERT OR UPDATE OF embedding ON text_embeddings
        FOR EACH ROW EXECUTE FUNCTION text_embeddings_bq_sync()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_text_embeddings_bq_sync ON text_embeddings")
    op.execute("DROP FUNCTION IF EXISTS text_embeddings_bq_sync()")
    op.execute("DROP TABLE IF EXISTS text_embeddings_bq")
