"""Record CBETA's licence on its data_sources row.

The cbeta row carried no licence metadata at all (license_spdx etc. were NULL),
so anything reading licences from the database — the alignment dataset export's
``source_licenses``, the EPUB/TXT/HTML/DOCX export rights page — had nothing to
show for 60 % of the corpus.

Source: https://www.cbeta.org/copyright.php, read 2026-11-11 —
"本資料庫未特別說明處則採用「Creative Commons 姓名標示-非商業性-相同方式分享 3.0 台灣
(中華民國) 授權條款」授權". SPDX has no identifier for the Taiwan port, so
``license_spdx`` holds the generic CC-BY-NC-SA-3.0 and the URL / notes name the
port. ``embedding_allowed`` is left untouched — the statement does not address it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0190"
down_revision: str | None = "0189"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOTES = (
    "CC BY-NC-SA 3.0 台灣 (中華民國). CBETA 使用說明 adds: 限個人或團體非營利性用途；"
    "再傳播、節錄引用及再加工發行時以不改變實質內容為原則，並需於成品附上本說明及版本資訊。"
    "Not covered by CC: 印順法師佛學著作集、太虛大師全書（印順文教基金會）、呂澂佛學著作集."
)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            UPDATE data_sources
               SET license_spdx = 'CC-BY-NC-SA-3.0',
                   license_url = 'https://creativecommons.org/licenses/by-nc-sa/3.0/tw/',
                   license_notes = :notes,
                   attribution_required = true,
                   commercial_allowed = false,
                   redistribution_allowed = true,
                   license_verified_at = '2026-11-11T00:00:00+08:00'
             WHERE code = 'cbeta'
            """
        ),
        {"notes": NOTES},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            UPDATE data_sources
               SET license_spdx = NULL, license_url = NULL, license_notes = NULL,
                   attribution_required = NULL, commercial_allowed = NULL,
                   redistribution_allowed = NULL, license_verified_at = NULL
             WHERE code = 'cbeta'
            """
        )
    )
