"""fix 6 data source URLs: moved sites, expired domains, HTTP-only

- shuge-guji: new.shuge.org 301→www.shuge.org (update to final URL)
- nlc-zhgjzhh: zhgj.nlc.cn down → guji.nlc.cn (中华古籍智慧化服务平台)
- wenzhou-guji: oec.wzlib.cn down → oyjy.wzlib.cn (瓯越记忆)
- jilin-guji: jlplib.com.cn domain expired → jilinlib.cn
- sd-mingdzj: sdgj.sdlib.com down → guji.sdlib.com
- xueheng: HTTPS not supported → HTTP

Revision ID: 0049
Revises: 0048
Create Date: 2026-03-04
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0049"
down_revision: Union[str, None] = "0048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (code, old_url, new_url)
FIXES = [
    ("shuge-guji", "https://new.shuge.org/", "https://www.shuge.org/"),
    ("nlc-zhgjzhh", "https://zhgj.nlc.cn/", "https://guji.nlc.cn/"),
    ("wenzhou-guji", "https://oec.wzlib.cn/", "https://oyjy.wzlib.cn/"),
    ("jilin-guji", "https://www.jlplib.com.cn/", "https://www.jilinlib.cn/"),
    ("sd-mingdzj", "https://sdgj.sdlib.com/dzj/", "http://guji.sdlib.com/"),
    ("xueheng", "https://www.xueheng.net/", "http://www.xueheng.net/"),
]


def upgrade() -> None:
    for code, _old, new in FIXES:
        op.execute(
            f"UPDATE data_sources SET base_url = '{new}' WHERE code = '{code}'"
        )


def downgrade() -> None:
    for code, old, _new in FIXES:
        op.execute(
            f"UPDATE data_sources SET base_url = '{old}' WHERE code = '{code}'"
        )
