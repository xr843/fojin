"""Reorder 中国大陆 sources: high-quality sources first.

New order for top sources:
  1. cbeta-cn          (-20)  CBETA大藏经下载(大陆档案站)
  2. books-fo          (-19)  AI佛书网
  3. yuezang           (-18)  大众阅藏(藏经矩阵)
  4. shidianguji       (-17)  识典古籍
  5. xuefo             (-16)  学点佛
  6. foyan             (-15)  佛研資訊
  7. dianjin           (-14)  典津
  8. texta-studio      (-13)  數字文獻學
  9. dunhuang-iiif     (-12)  敦煌遗书数据库
  10. dunhuang-academy  (-11)  数字敦煌
  11. qldzj            (-10)  乾隆大藏经
  12. hrfjw-dzj         (-9)  弘人法界网大藏经

Revision ID: 0114
Revises: 0113
"""

from alembic import op
from sqlalchemy import text

revision = "0114"
down_revision = "0113"
branch_labels = None
depends_on = None

UPDATES = [
    ("cbeta-cn", -20),
    ("books-fo", -19),
    ("yuezang", -18),
    ("shidianguji", -17),
    ("xuefo", -16),
    ("foyan", -15),
    ("dianjin", -14),
    ("texta-studio", -13),
    ("dunhuang-iiif", -12),
    ("dunhuang-academy", -11),
    ("qldzj", -10),
    ("hrfjw-dzj", -9),
]

ROLLBACK = [
    ("cbeta-cn", -10),
    ("books-fo", -8),
    ("yuezang", -5),
    ("shidianguji", 0),
    ("xuefo", -50),
    ("foyan", -52),
    ("dianjin", -9),
    ("texta-studio", -51),
    ("dunhuang-iiif", -7),
    ("dunhuang-academy", -6),
    ("qldzj", -4),
    ("hrfjw-dzj", -3),
]


def upgrade() -> None:
    for code, order in UPDATES:
        op.execute(text(f"UPDATE data_sources SET sort_order = {order} WHERE code = '{code}'"))


def downgrade() -> None:
    for code, order in ROLLBACK:
        op.execute(text(f"UPDATE data_sources SET sort_order = {order} WHERE code = '{code}'"))
