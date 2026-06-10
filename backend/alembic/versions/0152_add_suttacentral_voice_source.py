"""add suttacentral-voice data source

Revision ID: 0152
Revises: 0151
Create Date: 2026-06-10

Adds the SuttaCentral Voice source row that was missing from prod data
(surfaced by the post-Wave-1.2 e2e audit on 2026-06-10 — the License
backfill in 0149 covered ``suttacentral-voice`` but the source row
itself was never inserted, leading to 13/14 backfill matches instead
of 14/14).

voice.suttacentral.net is SuttaCentral's sister project providing
Pali sutta audio recordings with multilingual subtitles. Same CC0
mandate as the parent SuttaCentral.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0152"
down_revision: Union[str, None] = "0151"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa_text(
            """
            INSERT INTO data_sources (
                code, name_zh, name_en, base_url, description,
                access_type, region, languages, research_fields,
                supports_search, supports_fulltext,
                has_local_fulltext, has_remote_fulltext,
                supports_iiif, supports_api,
                sort_order, is_active, health_status,
                license_spdx, license_url, attribution_required,
                commercial_allowed, redistribution_allowed, embedding_allowed,
                license_notes, license_verified_at,
                created_at
            ) VALUES (
                'suttacentral-voice', 'SuttaCentral 语音',
                'SuttaCentral Voice',
                'https://voice.suttacentral.net',
                'SuttaCentral 姊妹项目，提供巴利经典的语音朗诵与多语字幕（含 en/de/id/my/si/vn 等）。母项目同 CC0 授权。',
                'external', '澳大利亚',
                'pi,en,de,id,my,si,vn', 'theravada',
                false, false, false, false, false, false,
                500, true, 'ok',
                'CC0-1.0',
                'https://creativecommons.org/publicdomain/zero/1.0/',
                false, true, true, true,
                'SuttaCentral Voice inherits the CC0 mandate of the parent SuttaCentral project. Audio + multilingual subtitles; not full-text indexed by fojin.',
                NOW(),
                NOW()
            )
            ON CONFLICT (code) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa_text("DELETE FROM data_sources WHERE code = 'suttacentral-voice'")
    )
