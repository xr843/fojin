"""如是我闻（rushiwowen）的数据源描述与实际不符（issue #1255）。

Revision ID: 0181
Revises: 0180
Create Date: 2026-10-05

0033 写入的描述是「中华大藏经总目录在线全文检索平台，提供经典原文与多版本大藏经
对照功能」。该站开发者在 #1255 指出本站并不提供多版本大藏经对照。2026-10-05 核对：
提 issue 的账号即该站页面上链接的 GitHub 账号；站点自己的 meta description 写的是
「收录来自 CBETA 的 4,515 部佛教典籍，提供原文与现代译文对照、AI 辅助释读与问答，
支持中英日三语阅读」——没有多版本对照，也不是「中华大藏经总目录」。新描述按站点
自述写，比 issue 里建议的文字多保留了「现代译文对照、AI 释读与问答」两项（站点确有）。

只改 code='rushiwowen' 且描述仍是旧值的那一行；downgrade 原样还原。
data_sources.embedding 是用含描述的文本算的，迁移不动它，上线后单独重算这一行。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0181"
down_revision: str | None = "0180"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = "中华大藏经总目录在线全文检索平台，提供经典原文与多版本大藏经对照功能"
_NEW = "免费的汉文佛典在线阅读与检索平台，经文取自 CBETA，提供原文与现代译文对照、AI 辅助释读与问答，并有 AI 辅助的英文、日文译文"


def _swap(old: str, new: str) -> None:
    op.get_bind().execute(
        sa.text("UPDATE data_sources SET description = :new WHERE code = 'rushiwowen' AND description = :old"),
        {"new": new, "old": old},
    )


def upgrade() -> None:
    _swap(_OLD, _NEW)


def downgrade() -> None:
    _swap(_NEW, _OLD)
