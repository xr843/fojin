"""Normalize sources metadata: region labels, has_local_fulltext backfill, fill known-null regions.

Three idempotent data fixes surfaced by the sources-page audit:

1. Region label duplicates: four Mongolia entries split across `蒙古` (3) and
   `蒙古国` (1). Normalize all to `蒙古国` (precise country name, matches other
   entries like `韩国`, `泰国`).

2. `has_local_fulltext` was almost never flipped to true even as ingestion
   progressed — only 2 of 532 sources had it set. Recompute from the current
   state of `buddhist_texts`: a source is "locally fulltext" when at least one
   linked text has `has_content=true`.

3. Fill region for sources where the publishing institution is unambiguous
   from the `code` prefix (DILA → 中国台湾, BuddhaSpace → 中国台湾, Cologne
   Digital Sanskrit Lexicon → 德国, Pali Text Society → 英国, Rangjung Yeshe →
   国际). Ambiguous single-work dictionaries (weishi, tiantai, sanzang-fashu,
   ...) are left for a later UI-side "工具书" bucket decision and not touched here.

Revision ID: 0122
Revises: 0121
"""

from alembic import op
from sqlalchemy import text

revision = "0122"
down_revision = "0121"
branch_labels = None
depends_on = None


# (code, new_region) — conservative, only codes whose origin is unambiguous.
REGION_FILLS: list[tuple[str, str]] = [
    # DILA (Dharma Drum / 法鼓佛教学院, 中国台湾)
    ("dila-dfb", "中国台湾"),
    ("dila-nanshanlu", "中国台湾"),
    ("dila-plc", "中国台湾"),
    ("dila-hopkins", "中国台湾"),
    ("dila-mvp", "中国台湾"),
    ("dila-ptg", "中国台湾"),
    ("dila-soothill", "中国台湾"),
    # BuddhaSpace (buddhaspace.org, 庄春江居士团队, 中国台湾)
    ("bs-faxiang", "中国台湾"),
    ("bs-yiqiejing-yinyi", "中国台湾"),
    ("bs-xu-yinyi", "中国台湾"),
    ("bs-suihan-lu", "中国台湾"),
    ("bs-fanfanyu", "中国台湾"),
    ("bs-agama", "中国台湾"),
    ("bs-changjianci", "中国台湾"),
    # Cologne Digital Sanskrit Lexicon (University of Cologne)
    ("cdsl-mw", "德国"),
    ("cdsl-bhs", "德国"),
    ("cdsl-apte", "德国"),
    # Pali Text Society
    ("pts-ped", "英国"),
    ("ncped", "英国"),
    ("dppn", "英国"),
    # Rangjung Yeshe Wiki — run by an international Tibetan Buddhist community
    ("rangjung-yeshe", "国际"),
]


def upgrade() -> None:
    # 1. Region label normalization: 蒙古 → 蒙古国
    op.execute(
        text("UPDATE data_sources SET region = '蒙古国' WHERE region = '蒙古'")
    )

    # 2. Backfill has_local_fulltext based on current buddhist_texts state.
    #    Sync both directions so the flag reflects reality even if content was removed.
    op.execute(
        text(
            """
            UPDATE data_sources ds
            SET has_local_fulltext = EXISTS (
                SELECT 1 FROM buddhist_texts bt
                WHERE bt.source_id = ds.id AND bt.has_content = true
            )
            """
        )
    )

    # 3. Fill unambiguous null regions.
    for code, region in REGION_FILLS:
        op.execute(
            text("UPDATE data_sources SET region = :r WHERE code = :c AND region IS NULL").bindparams(
                r=region, c=code
            )
        )


def downgrade() -> None:
    # 3. Revert region fills (only where we set the value we'd expect).
    for code, region in REGION_FILLS:
        op.execute(
            text("UPDATE data_sources SET region = NULL WHERE code = :c AND region = :r").bindparams(
                c=code, r=region
            )
        )

    # 2. has_local_fulltext: no principled reverse — resetting all to false is
    #    destructive, and the upgrade is idempotent so downgrade/re-upgrade is a
    #    no-op data-wise. Leave the computed values in place.

    # 1. Region normalization: restore the three pre-upgrade `蒙古` rows
    #    (bdrc-nlm, mongolia-academy, eap-dambadarjaa). The fourth Mongolia
    #    source (mongolian-kanjur-nlm) was already `蒙古国` and is left alone.
    op.execute(
        text(
            "UPDATE data_sources SET region = '蒙古' "
            "WHERE code IN ('bdrc-nlm', 'mongolia-academy', 'eap-dambadarjaa')"
        )
    )
