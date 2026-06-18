"""dedup kg_entities persons by DILA id, then add a unique guard

Revision ID: 0159
Revises: 0158
Create Date: 2026-06-18

The daily DILA person sync (scripts/sync_dila_combined.py) read a snapshot of
existing dila ids then bulk-INSERTed new ones with no DB-level uniqueness — so
two concurrent runs (cron + webhook CD + manual) could both insert the same
person. A flock guarded same-host concurrency only, leaving the database with
no protection. The result, observed in prod: 21 dila ids duplicated across 22
extra rows, and crucially they are foundational translators (鳩摩羅什, 龍樹,
世親, 佛馱跋陀羅, 竺法護 …) whose knowledge-graph relations got split across the
duplicate entities — a scholar opening 鳩摩羅什 saw only half his relations.

This migration is a one-time cleanup + a permanent guard. For every dila id
with duplicates it keeps the lowest id as canonical, merges any name/description
fields the canonical lacks from the losers, re-points the losers' kg_relations
to the canonical (dropping the ones the canonical already has, since kg_relations
carries unique indexes on the (subject, predicate, object[, source]) triple),
deletes the now-unreferenced loser entities, and finally builds a PARTIAL unique
index on (external_ids->>'dila'). The companion change in sync_dila_combined.py
adds ON CONFLICT DO NOTHING so the database — not script discipline — is the
source of truth.

Verified by a BEGIN/ROLLBACK dry-run on prod: 22 losers, 49 relations re-pointed,
154 redundant relations dropped (49+154 = the 203 that referenced losers), the
4 pre-existing self-loops on unrelated entities left untouched, 0 duplicate
groups remaining, index builds clean. The dedup is irreversible, so downgrade
only drops the index.

kg_relations FK columns have no ON DELETE clause, so re-pointing the relations
BEFORE deleting the loser entities is mandatory (a plain delete would be blocked
by the foreign key). Each statement recomputes the loser→canonical map inline so
it carries no cross-statement temp-table state and is idempotent: after the first
run there are no duplicate groups, the map is empty, and every step is a no-op.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0159"
down_revision: str | None = "0158"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Reusable loser→canonical map: every duplicated person dila id keeps MIN(id).
_MAP_CTE = """
WITH dups AS (
    SELECT external_ids->>'dila' AS dila, MIN(id) AS canonical
    FROM kg_entities
    WHERE entity_type = 'person' AND external_ids->>'dila' IS NOT NULL
    GROUP BY external_ids->>'dila'
    HAVING COUNT(*) > 1
),
m AS (
    SELECT e.id AS loser, d.canonical
    FROM kg_entities e
    JOIN dups d ON e.external_ids->>'dila' = d.dila
    WHERE e.id <> d.canonical
)
"""

# 1. Fill canonical fields the canonical is missing from its losers.
_MERGE_FIELDS = _MAP_CTE + """,
lf AS (
    SELECT m.canonical AS c,
        MAX(l.name_en)     FILTER (WHERE l.name_en     IS NOT NULL) AS name_en,
        MAX(l.name_sa)     FILTER (WHERE l.name_sa     IS NOT NULL) AS name_sa,
        MAX(l.name_pi)     FILTER (WHERE l.name_pi     IS NOT NULL) AS name_pi,
        MAX(l.name_bo)     FILTER (WHERE l.name_bo     IS NOT NULL) AS name_bo,
        MAX(l.description) FILTER (WHERE l.description IS NOT NULL) AS description
    FROM m
    JOIN kg_entities l ON l.id = m.loser
    GROUP BY m.canonical
)
UPDATE kg_entities c SET
    name_en     = COALESCE(c.name_en, lf.name_en),
    name_sa     = COALESCE(c.name_sa, lf.name_sa),
    name_pi     = COALESCE(c.name_pi, lf.name_pi),
    name_bo     = COALESCE(c.name_bo, lf.name_bo),
    description = COALESCE(c.description, lf.description)
FROM lf
WHERE c.id = lf.c
"""

# 2. Drop loser relations that would collapse to a self-loop once both endpoints
#    are canonicalized (a relation between two aliases of the same person). The
#    "references a loser" guard keeps pre-existing self-loops on other entities
#    untouched. (No-op on current prod data, kept as a correctness guard.)
_DROP_WOULDBE_SELFLOOPS = _MAP_CTE + """
DELETE FROM kg_relations r
WHERE (r.subject_id IN (SELECT loser FROM m) OR r.object_id IN (SELECT loser FROM m))
  AND COALESCE((SELECT canonical FROM m WHERE loser = r.subject_id), r.subject_id)
    = COALESCE((SELECT canonical FROM m WHERE loser = r.object_id), r.object_id)
"""

# 3. Re-point subject, skipping any that would duplicate a triple the canonical
#    already owns (those losers stay referenced and are swept in step 5). The
#    MIN(id) clause also keeps only one survivor when two sibling losers of the
#    same canonical carry the same (predicate, object) — re-pointing both in one
#    statement would otherwise collide on uq_kg_relation_triple and abort.
_REPOINT_SUBJECT = _MAP_CTE + """
UPDATE kg_relations r SET subject_id = m.canonical
FROM m
WHERE r.subject_id = m.loser
  AND NOT EXISTS (
      SELECT 1 FROM kg_relations r2
      WHERE r2.subject_id = m.canonical
        AND r2.predicate = r.predicate
        AND r2.object_id = r.object_id
        AND r2.id <> r.id
  )
  AND r.id = (
      SELECT MIN(r3.id) FROM kg_relations r3
      JOIN m m3 ON m3.loser = r3.subject_id
      WHERE m3.canonical = m.canonical
        AND r3.predicate = r.predicate
        AND r3.object_id = r.object_id
  )
"""

# 4. Re-point object, same guard (incl. the sibling-loser MIN(id) tie-breaker).
_REPOINT_OBJECT = _MAP_CTE + """
UPDATE kg_relations r SET object_id = m.canonical
FROM m
WHERE r.object_id = m.loser
  AND NOT EXISTS (
      SELECT 1 FROM kg_relations r2
      WHERE r2.object_id = m.canonical
        AND r2.predicate = r.predicate
        AND r2.subject_id = r.subject_id
        AND r2.id <> r.id
  )
  AND r.id = (
      SELECT MIN(r3.id) FROM kg_relations r3
      JOIN m m3 ON m3.loser = r3.object_id
      WHERE m3.canonical = m.canonical
        AND r3.predicate = r.predicate
        AND r3.subject_id = r.subject_id
  )
"""

# 5. Delete the redundant relations left pointing at a loser (the canonical
#    already has the equivalent triple).
_DELETE_REDUNDANT_RELATIONS = _MAP_CTE + """
DELETE FROM kg_relations r USING m
WHERE r.subject_id = m.loser OR r.object_id = m.loser
"""

# 6. Delete the now-unreferenced loser entities.
_DELETE_LOSERS = _MAP_CTE + """
DELETE FROM kg_entities e USING m WHERE e.id = m.loser
"""

# 7. Permanent guard: one row per non-null dila id.
_CREATE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_kg_entities_dila
ON kg_entities ((external_ids->>'dila'))
WHERE external_ids->>'dila' IS NOT NULL
"""


def upgrade() -> None:
    op.execute(_MERGE_FIELDS)
    op.execute(_DROP_WOULDBE_SELFLOOPS)
    op.execute(_REPOINT_SUBJECT)
    op.execute(_REPOINT_OBJECT)
    op.execute(_DELETE_REDUNDANT_RELATIONS)
    op.execute(_DELETE_LOSERS)
    op.execute(_CREATE_INDEX)


def downgrade() -> None:
    # The dedup (merged fields, re-pointed/dropped relations, deleted entities)
    # is irreversible; only the guard index can be removed.
    op.execute("DROP INDEX IF EXISTS ux_kg_entities_dila")
