"""fix data_sources.name_en quality: 6 underscore slugs + 8 missing

Revision ID: 0154
Revises: 0153
Create Date: 2026-06-12

The name_en column has existed since the source-governance backfill and is
populated for 605/613 active sources, but the frontend never read it (#707).
Before wiring it up, fix the residue a quality audit found: six values are
underscore slugs (Fo_Guang_Buddhist_Dictionary) rather than display names,
and eight rows are NULL/empty. After this migration every active source has
a display-quality English name.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0154"
down_revision: str | None = "0153"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# code -> display-quality English name
FIXES = {
    # underscore slugs → proper names
    "fanyi-mingyi": "Fanyi Mingyi Ji (Compendium of Translated Terms)",
    "foguang": "Fo Guang Dictionary of Buddhism",
    "sanzang-fashu": "Sanzang Fashu (Numerical Buddhist Terms)",
    "suyu-foyuan": "Buddhist Origins of Chinese Idioms",
    "tiantai": "Tiantai Teachings Dictionary",
    "weishi": "Yogacara Glossary (Vernacular Explanations)",
    # missing → filled
    "dict-fo": "Foxue Cidian (Buddhist Dictionary)",
    "kandianguji": "Kandian Guji (Chinese Classics)",
    "mugenzo": "Mugenzo Buddhist Library",
    "pan": "Theravada Chinese Resources",
    "plumvillage": "Living Gems (Plum Village)",
    "rushi-guji-tools": "Rushi Guji Toolkit",
    "shu-fo": "Foshu Buddhist Books",
    "wx": "Theravada Chinese Resources Collection",
}


def upgrade() -> None:
    for code, name_en in FIXES.items():
        op.execute(
            "UPDATE data_sources SET name_en = '{}' WHERE code = '{}'".format(
                name_en.replace("'", "''"), code.replace("'", "''")
            )
        )


def downgrade() -> None:
    # Data-quality fix; the previous slugs/NULLs are not worth restoring.
    pass
