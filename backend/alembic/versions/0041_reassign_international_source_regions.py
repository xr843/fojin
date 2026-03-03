"""reassign 23 sources from 国际 to specific countries

根据运营机构所在地，将可明确归属的数据源从"国际"重新分配到具体国家/地区。

Revision ID: 0041
Revises: 0040
Create Date: 2026-03-03
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0041"
down_revision: Union[str, None] = "0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (region, [codes])
REASSIGNMENTS = [
    ("中国台湾", ["cbeta-org"]),
    ("中国大陆", ["rushiwowen"]),
    ("德国", ["stonesutras", "open-philology"]),
    ("英国", ["eap-bl"]),
    ("俄罗斯", ["ilp-tangut"]),
    ("日本", ["kanseki-repo"]),
    ("澳大利亚", ["suttacentral-org", "suttacentral-voice", "early-buddhist-texts", "nti-reader"]),
    ("美国", [
        "accesstoinsight", "asian-legacy-library", "bdk-tripitaka",
        "tbrc-bdrc", "dharmacloud", "dharma-dictionary", "rywiki",
        "khyentse-translation", "sacred-texts", "sanskritdocuments",
    ]),
    ("荷兰", ["ctext"]),
    ("捷克", ["sketchengine-sanskrit"]),
]


def upgrade() -> None:
    for region, codes in REASSIGNMENTS:
        placeholders = ", ".join(f"'{c}'" for c in codes)
        op.execute(
            f"UPDATE data_sources SET region = '{region}' "
            f"WHERE code IN ({placeholders}) AND region = '国际'"
        )


def downgrade() -> None:
    for _, codes in REASSIGNMENTS:
        placeholders = ", ".join(f"'{c}'" for c in codes)
        op.execute(
            f"UPDATE data_sources SET region = '国际' "
            f"WHERE code IN ({placeholders})"
        )
