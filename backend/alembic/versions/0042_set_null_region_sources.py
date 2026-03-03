"""set region for 14 original seed sources that had NULL region

Revision ID: 0042
Revises: 0041
Create Date: 2026-03-03
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0042"
down_revision: Union[str, None] = "0041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ASSIGNMENTS = {
    "美国": ["84000", "bdrc", "dsbc"],
    "中国台湾": ["cbeta", "dila"],
    "泰国": ["budsir"],
    "韩国": ["ktk"],
    "日本": ["sat", "ddb"],
    "德国": ["gretil"],
    "英国": ["idp"],
    "挪威": ["polyglotta"],
    "澳大利亚": ["suttacentral"],
    "印度": ["vri"],
}


def upgrade() -> None:
    for region, codes in ASSIGNMENTS.items():
        placeholders = ", ".join(f"'{c}'" for c in codes)
        op.execute(
            f"UPDATE data_sources SET region = '{region}' "
            f"WHERE code IN ({placeholders}) AND region IS NULL"
        )


def downgrade() -> None:
    all_codes = [c for codes in ASSIGNMENTS.values() for c in codes]
    placeholders = ", ".join(f"'{c}'" for c in all_codes)
    op.execute(
        f"UPDATE data_sources SET region = NULL WHERE code IN ({placeholders})"
    )
