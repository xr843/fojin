"""add composite (source_id, headword) index on dictionary_entries

辞典浏览模式（WHERE source_id=X ORDER BY headword LIMIT 50）此前无法命中复合索引，
planner 选 ix_dictionary_entries_headword 全索引扫描后过滤 source_id，
36 万行表上 EXPLAIN 实测 9.7 秒。

加复合 (source_id, headword) 后，planner 直接走该索引：先定位 source_id 子集，
再按 headword 顺序取 LIMIT 50，预计降至个位数毫秒。

Revision ID: 0131
Revises: 0130
Create Date: 2026-05-11
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0131"
down_revision: Union[str, None] = "0130"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CONCURRENTLY: avoid AccessExclusiveLock on a 360k-row hot table.
    # Must run outside a transaction.
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_dict_entries_source_headword",
            "dictionary_entries",
            ["source_id", "headword"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_dict_entries_source_headword",
            table_name="dictionary_entries",
            postgresql_concurrently=True,
            if_exists=True,
        )
