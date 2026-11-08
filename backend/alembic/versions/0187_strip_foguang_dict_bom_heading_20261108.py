"""Strip the import artefact heading from every 佛光大辭典 definition.

All 32,132 佛光大辭典 rows in ``dictionary_entries`` start with ``一`` + U+FEFF
(byte-order mark) + a heading line + newline, e.g. ``一<U+FEFF>色即是空\n梵語 …``.
The ``一`` and the BOM are left-overs of the original import, not content; the
heading line repeats the headword (34 rows carry an OCR-typo / variant-glyph copy
of it, e.g. 善薩行 for 菩薩行, which is worse than nothing). Readers saw the stray
「一」 at the top of every 佛光大辭典 entry — in the reader's selection popover,
the dictionary page and the crawler-facing /dict pages — and it was fed into RAG
prompts too. Found 2026-11-08 from a user screenshot of 色即是空.

Two rows (舊善, 衣裓) have no newline: heading and definition are
separated by spaces, so for those only the ``一<U+FEFF><headword>`` prefix and the
following whitespace go.

Every changed row's original text is copied to
``dictionary_entries_bom_backup_20261108`` first; ``downgrade`` restores from it.
Only ``dictionary_entries.definition`` holds this text (term-concept previews are
computed on read; dictionary text is not in Elasticsearch).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0187"
down_revision: str | None = "0186"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BACKUP = "dictionary_entries_bom_backup_20261108"
# U+FEFF written via chr() in SQL so the migration file itself stays BOM-free.
PREFIX = "'一' || chr(65279)"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {BACKUP} AS
        SELECT id, definition FROM dictionary_entries
         WHERE definition LIKE {PREFIX} || '%'
        """
    )
    # 1) 一 + BOM + heading line + newline → drop through the first newline
    op.execute(
        f"""
        UPDATE dictionary_entries
           SET definition = substr(definition, strpos(definition, E'\\n') + 1)
         WHERE definition LIKE {PREFIX} || '%'
           AND strpos(definition, E'\\n') > 0
           AND strpos(definition, E'\\n') <= 2 + char_length(headword) + 40
        """
    )
    # 2) no newline (heading and text separated by spaces): drop 一 + BOM + headword + whitespace
    op.execute(
        f"""
        UPDATE dictionary_entries
           SET definition = ltrim(substr(definition, 3 + char_length(headword)), E' \\t\\u3000')
         WHERE definition LIKE {PREFIX} || headword || '%'
        """
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
