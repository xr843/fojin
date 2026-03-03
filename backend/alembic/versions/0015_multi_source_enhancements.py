"""multi-source enhancements: extend cbeta_id, add title_en, text_contents lang, import_logs

Revision ID: 0015
Revises: 0014
Create Date: 2026-03-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extend cbeta_id from VARCHAR(50) to VARCHAR(200)
    op.alter_column(
        "buddhist_texts",
        "cbeta_id",
        existing_type=sa.String(50),
        type_=sa.String(200),
    )

    # Add title_en column
    op.add_column(
        "buddhist_texts",
        sa.Column("title_en", sa.String(500), nullable=True),
    )

    # Add lang column to text_contents
    op.add_column(
        "text_contents",
        sa.Column("lang", sa.String(10), server_default="lzh", nullable=False),
    )

    # Drop old unique constraint and create new one with lang
    op.drop_constraint("uq_text_content_text_juan", "text_contents", type_="unique")
    op.create_unique_constraint(
        "uq_text_content_text_juan_lang",
        "text_contents",
        ["text_id", "juan_num", "lang"],
    )

    # Create import_logs table
    op.create_table(
        "import_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_code", sa.String(50), nullable=False, index=True),
        sa.Column(
            "status",
            sa.String(20),
            server_default="running",
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stats_json", sa.JSON(), nullable=True),
        sa.Column("error_log", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("import_logs")

    op.drop_constraint("uq_text_content_text_juan_lang", "text_contents", type_="unique")
    op.create_unique_constraint(
        "uq_text_content_text_juan",
        "text_contents",
        ["text_id", "juan_num"],
    )

    op.drop_column("text_contents", "lang")
    op.drop_column("buddhist_texts", "title_en")

    op.alter_column(
        "buddhist_texts",
        "cbeta_id",
        existing_type=sa.String(200),
        type_=sa.String(50),
    )
