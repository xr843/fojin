"""purge catalog/TOC/production-note junk rows from dictionary_entries

Revision ID: 0161
Revises: 0160
Create Date: 2026-06-26

Some source dictionaries embedded their catalog structure / production notes as
"entries": e.g. ``00000製作說明【阿彌陀佛】``, ``00 總目錄``,
``001-01 教義類〈一般教義〉`` (中華佛教百科全書 section headers). These are not
lexical terms — they sort to the very top of a dictionary's browse view
(ASCII digits precede CJK) and were the first thing a user saw.

Buddhist headwords use Chinese numerals (一二三), never a leading ASCII digit, so
``headword ~ '^[0-9]'`` is a safe junk filter. Verified on prod before writing:
83 such rows, all catalog/TOC/製作說明 metadata, with 0 term_concept_entries
referencing them. The importer (import_dila_dict.py) now skips the same pattern
so they don't return on re-import.

Irreversible by nature (deleted junk can't be restored); downgrade is a no-op.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0161"
down_revision: str | None = "0160"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM dictionary_entries WHERE headword ~ '^[0-9]'")


def downgrade() -> None:
    # Deleted rows were junk metadata and cannot be reconstructed.
    pass
