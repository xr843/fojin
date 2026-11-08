"""Compose decomposed Latin diacritics (IAST / Pāli / Manchu transliteration) in dictionary text.

About 1,350 ``dictionary_entries`` definitions — PTS 巴英辞典 1,014, 五體清文鑑 167,
四譯合璧輯要 164, plus a handful elsewhere — write romanised Pāli/Sanskrit/Manchu with
*decomposed* diacritics (``u`` + U+0304 combining macron instead of ``ū``). Many
fonts misplace a combining mark after a letter they draw from a different fallback
font, and a reader copying ``ū`` cannot find text stored as ``u``+U+0304.

Only runs of a Latin letter followed by combining marks (U+0300–U+036F) are
NFC-composed. A blanket ``normalize(definition, NFC)`` is wrong here: NFC also
folds CJK compatibility ideographs (U+F900–U+FAFF) into their unified forms, and
the 音義 dictionaries (可洪, 慧琳) and NTI use exactly those code points to keep
variant glyphs apart — 226 rows would lose distinctions the source makes on
purpose. Headwords are untouched (none contain Latin + combining marks).

Original text of every changed row goes to ``dictionary_entries_nfc_backup_20261108``
first; ``downgrade`` restores from it.
"""

import re
import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0188"
down_revision: str | None = "0187"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BACKUP = "dictionary_entries_nfc_backup_20261108"
# A Latin letter (basic, Latin-1, Extended-A/B, Extended Additional) + one or more combining marks.
LATIN_RUN = re.compile(r"[A-Za-z\u00C0-\u024F\u1E00-\u1EFF][\u0300-\u036F]+")
SQL_FILTER = r"definition ~ '[A-Za-z\u00C0-\u024F\u1E00-\u1EFF][\u0300-\u036f]'"


def compose_latin(text: str) -> str:
    """NFC only the Latin-letter + combining-mark runs; leave every other character as is."""
    return LATIN_RUN.sub(lambda m: unicodedata.normalize("NFC", m.group()), text)


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(f"SELECT id, definition FROM dictionary_entries WHERE {SQL_FILTER}")).all()
    changed = [(r.id, r.definition, compose_latin(r.definition)) for r in rows]
    changed = [c for c in changed if c[2] != c[1]]
    op.execute(f"CREATE TABLE IF NOT EXISTS {BACKUP} (id integer PRIMARY KEY, definition text NOT NULL)")
    if not changed:
        return
    bind.execute(
        sa.text(f"INSERT INTO {BACKUP} (id, definition) VALUES (:id, :d) ON CONFLICT (id) DO NOTHING"),
        [{"id": i, "d": old} for i, old, _ in changed],
    )
    bind.execute(
        sa.text("UPDATE dictionary_entries SET definition = :d WHERE id = :id"),
        [{"id": i, "d": new} for i, _, new in changed],
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE dictionary_entries d
           SET definition = b.definition
          FROM {BACKUP} b
         WHERE b.id = d.id
        """
    )
    op.execute(f"DROP TABLE IF EXISTS {BACKUP}")
