"""split supports_fulltext into has_local_fulltext and has_remote_fulltext

Revision ID: 0028
Revises: 0027
Create Date: 2026-03-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "data_sources",
        sa.Column("has_local_fulltext", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "data_sources",
        sa.Column("has_remote_fulltext", sa.Boolean(), server_default="false", nullable=False),
    )

    # Backfill: CBETA variants have local fulltext (texts ingested into our DB)
    op.execute(
        "UPDATE data_sources SET has_local_fulltext = true "
        "WHERE code IN ('cbeta', 'cbeta-org', 'cbeta-api')"
    )
    # Backfill: sources with remote fulltext reading (external sites with full text)
    op.execute(
        "UPDATE data_sources SET has_remote_fulltext = true "
        "WHERE code IN ('shidianguji', 'dianjin', "
        "'suttacentral', 'suttacentral-org', "
        "'84000', 'accesstoinsight', 'ctext', 'sat', 'kanseki-repo', "
        "'dharmacloud', 'lotsawa-house', 'dhammatalks', 'buddhanexus')"
    )
    # Update supports_fulltext only for rows where new columns are set,
    # preserving any existing supports_fulltext=true from earlier migrations.
    op.execute(
        "UPDATE data_sources SET supports_fulltext = true "
        "WHERE has_local_fulltext = true OR has_remote_fulltext = true"
    )


def downgrade() -> None:
    op.drop_column("data_sources", "has_remote_fulltext")
    op.drop_column("data_sources", "has_local_fulltext")
