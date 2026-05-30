"""Build the FRBR Work spine from existing buddhist_texts (idempotent backfill).

Populates works / work_witnesses / work_aliases purely additively — nothing in
buddhist_texts / text_identifiers / alignment_pairs is touched.

Each buddhist_text ends up in exactly ONE work. Assignment runs in four passes,
in priority order; once a text is claimed by a witness it is skipped by later
passes:

  Pass 1 — cross-pillar Skt-title clustering (the high-value bit)
      Every text with a non-empty title_sa is grouped by a normalized Skt-title
      key (lowercase + diacritics stripped + whitespace collapsed). Each distinct
      key becomes one Work that may span 漢 (T/X), 藏 (84K), and Skt (GRETIL)
      witnesses. alias(scheme='skt_title', value=<normkey>).

  Pass 2 — SuttaCentral works
      Each remaining `SC-<uid>` text → a Work anchored by sc_root_uid=<uid>,
      witness role='root' lang='pi' canon='pali' confidence='verified'.
      alias(scheme='sc_uid', value=<uid>).

  Pass 3 — 84000 works
      Each remaining `84K-toh<N>` text → a Work anchored by toh_number=<N>,
      witness role='translation' lang='bo' canon='kangyur' confidence='verified'.
      alias(scheme='toh', value=<N>).

  Pass 4 — singletons
      Every remaining text → a singleton Work keyed by its cbeta_id, so every
      text belongs to exactly one work. confidence='auto'.

Idempotency
-----------
Re-running is a no-op. Before each pass we load the set of text_ids that already
have a witness (from the DB plus an in-run set) and skip them. Works are reused
via their natural keys: alias (scheme, value) for Skt clusters, sc_root_uid for
SC, toh_number for 84000, and slug for singletons. UNIQUE(work_id, text_id) and
UNIQUE(scheme, value) are respected by lookup-before-insert.

Usage
-----
  python scripts/build_works.py --dry-run            # compute + log, no writes
  python scripts/build_works.py --dry-run --limit 500
  python scripts/build_works.py                      # write
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.text import BuddhistText
from app.models.work import Work, WorkAlias, WorkWitness

# ---------------------------------------------------------------------------
# Pure logic (no DB) — unit-testable in isolation
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")

# A Skt-title cluster larger than this is treated as an over-broad / class-level
# title (e.g. bare "Prajñāpāramitā" / "Sūtra" / "Dhāraṇī") and is NOT merged —
# its texts fall through to singleton works instead, so a single generic title
# can never silently fuse dozens of unrelated texts into one giant Work. Tune
# via --max-skt-cluster after inspecting the largest clusters with --dry-run.
MAX_SKT_CLUSTER_DEFAULT = 15


def normalize_skt_title(title: str | None) -> str:
    """Normalize a Sanskrit title to a clustering key.

    Lowercase, NFKD-decompose and drop combining marks (so ``ā``/``a``,
    ``ṣ``/``s``, ``ñ``/``n`` collapse), then collapse all whitespace runs to a
    single space and strip. Returns "" for empty/whitespace input.

    The diacritic-folding is deliberately aggressive: production Skt titles are
    transliterated inconsistently across pillars, so folding to ASCII letters is
    what actually merges ``Vajracchedikā`` with ``vajracchedika``.
    """
    if not title:
        return ""
    # NFKD then drop combining marks (category Mn).
    decomposed = unicodedata.normalize("NFKD", title)
    folded = "".join(c for c in decomposed if not unicodedata.combining(c))
    folded = folded.lower()
    folded = _WS_RE.sub(" ", folded).strip()
    return folded


def canon_from_cbeta_id(cbeta_id: str | None) -> str | None:
    """Map a cbeta_id prefix to a canon label.

    T... → taisho, X... → xuzang, SC-... → pali, 84K-toh... → kangyur,
    GRETIL-... → gretil, VRI-... → pali. Unknown → None.
    """
    if not cbeta_id:
        return None
    if cbeta_id.startswith("SC-"):
        return "pali"
    if cbeta_id.startswith("84K-toh"):
        return "kangyur"
    if cbeta_id.startswith("GRETIL-"):
        return "gretil"
    if cbeta_id.startswith("VRI-"):
        return "pali"
    if cbeta_id.startswith("T"):
        return "taisho"
    if cbeta_id.startswith("X"):
        return "xuzang"
    return None


def role_from_lang(lang: str | None) -> str:
    """root for primary-language witnesses (sa/pi), translation otherwise."""
    return "root" if lang in ("sa", "pi") else "translation"


def sanitize_slug_base(raw: str) -> str:
    """Sanitize an arbitrary string into a slug fragment ``[a-z0-9-]+``.

    Diacritics are folded (NFKD + drop combining marks), everything that is not
    ``[a-z0-9]`` becomes a hyphen, runs of hyphens collapse, and leading/trailing
    hyphens are stripped. Returns "" if nothing survives.
    """
    decomposed = unicodedata.normalize("NFKD", raw)
    folded = "".join(c for c in decomposed if not unicodedata.combining(c))
    folded = folded.lower()
    folded = _SLUG_STRIP_RE.sub("-", folded)
    return folded.strip("-")


def make_unique_slug(base: str, taken: set[str], *, fallback: str = "work") -> str:
    """Return a slug derived from ``base`` not present in ``taken``.

    ``base`` is sanitized first. On collision, append ``-2``, ``-3``, …. The
    returned slug is added to ``taken`` so successive calls stay unique within a
    run. Truncated to 200 chars to fit the column.
    """
    sanitized = sanitize_slug_base(base) or fallback
    sanitized = sanitized[:200]
    if sanitized not in taken:
        taken.add(sanitized)
        return sanitized
    n = 2
    while True:
        suffix = f"-{n}"
        candidate = f"{sanitized[: 200 - len(suffix)]}{suffix}"
        if candidate not in taken:
            taken.add(candidate)
            return candidate
        n += 1


def pick_display_title(group: list[BuddhistText], norm_key: str) -> str:
    """Best display title for a Skt cluster: prefer a 漢 title, else the Skt one.

    A zh title is preferred because it is the most human-readable for FoJin's
    primary audience. Falls back to any text's title_sa, then the raw norm_key.
    """
    for t in group:
        if t.title_zh and t.title_zh.strip():
            return t.title_zh.strip()
    for t in group:
        if t.title_sa and t.title_sa.strip():
            return t.title_sa.strip()
    return norm_key


def representative_skt_title(group: list[BuddhistText]) -> str | None:
    """A representative original (un-normalized) Skt title for the cluster."""
    for t in group:
        if t.title_sa and t.title_sa.strip():
            return t.title_sa.strip()
    return None


def toh_number_from_cbeta_id(cbeta_id: str) -> str:
    """Extract ``<N>`` from ``84K-toh<N>`` (returns the part after ``84K-toh``)."""
    return cbeta_id[len("84K-toh"):]


def sc_uid_from_cbeta_id(cbeta_id: str) -> str:
    """Extract ``<uid>`` from ``SC-<uid>``."""
    return cbeta_id[len("SC-"):]


# ---------------------------------------------------------------------------
# Build engine (DB-bound)
# ---------------------------------------------------------------------------


@dataclass
class BuildStats:
    works_created: int = 0
    witnesses_created: int = 0
    aliases_created: int = 0
    per_pass: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    # (normalized key, size) of the largest Skt-title clusters, for inspection.
    top_skt_clusters: list[tuple[str, int]] = field(default_factory=list)
    # clusters skipped for exceeding --max-skt-cluster (left as singletons).
    skipped_skt_clusters: list[tuple[str, int]] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "=== build_works summary ===",
            f"works created:     {self.works_created}",
            f"witnesses created: {self.witnesses_created}",
            f"aliases created:   {self.aliases_created}",
            "witnesses per pass:",
        ]
        for name in ("pass1_skt", "pass2_sc", "pass3_toh", "pass4_singleton"):
            lines.append(f"  {name:<16} {self.per_pass.get(name, 0)}")
        if self.top_skt_clusters:
            lines.append("largest Skt-title clusters (size × key) — eyeball these:")
            for key, size in self.top_skt_clusters:
                lines.append(f"  {size:>4}  {key[:70]}")
        if self.skipped_skt_clusters:
            lines.append(
                f"SKIPPED {len(self.skipped_skt_clusters)} over-broad cluster(s) "
                "(> --max-skt-cluster) — left as singletons:"
            )
            for key, size in self.skipped_skt_clusters:
                lines.append(f"  {size:>4}  {key[:70]}")
        return "\n".join(lines)


class WorkBuilder:
    """Stateful, idempotent builder over an open AsyncSession.

    Caches in-run lookups so a single run never double-creates, and consults the
    DB up front so a *second* run is a no-op.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        dry_run: bool,
        stats: BuildStats,
        max_skt_cluster: int = MAX_SKT_CLUSTER_DEFAULT,
    ):
        self.session = session
        self.dry_run = dry_run
        self.stats = stats
        self.max_skt_cluster = max_skt_cluster
        # text_id -> already has a witness (DB or this run)
        self.assigned_text_ids: set[int] = set()
        # natural-key -> Work (reused across passes / runs)
        self.work_by_alias: dict[tuple[str, str], Work] = {}
        self.work_by_sc_uid: dict[str, Work] = {}
        self.work_by_toh: dict[str, Work] = {}
        self.work_by_slug: dict[str, Work] = {}
        self.taken_slugs: set[str] = set()
        # (scheme, value) already present (DB or this run)
        self.existing_aliases: set[tuple[str, str]] = set()

    async def load_existing(self) -> None:
        """Prime caches from the DB so re-runs reuse rather than duplicate."""
        works = (await self.session.execute(select(Work))).scalars().all()
        for w in works:
            self.taken_slugs.add(w.slug)
            self.work_by_slug[w.slug] = w
            if w.sc_root_uid:
                self.work_by_sc_uid[w.sc_root_uid] = w
            if w.toh_number:
                self.work_by_toh[w.toh_number] = w

        aliases = (await self.session.execute(select(WorkAlias))).scalars().all()
        # work_id -> Work, to attach aliased works into the alias cache.
        works_by_id = {w.id: w for w in works}
        for a in aliases:
            self.existing_aliases.add((a.scheme, a.value))
            w = works_by_id.get(a.work_id)
            if w is not None:
                self.work_by_alias[(a.scheme, a.value)] = w

        witnesses = (await self.session.execute(select(WorkWitness.text_id))).all()
        for (text_id,) in witnesses:
            self.assigned_text_ids.add(text_id)

    # -- low-level helpers ---------------------------------------------------

    def _new_work(self, **kwargs) -> Work:
        work = Work(**kwargs)
        if not self.dry_run:
            self.session.add(work)
        self.stats.works_created += 1
        self.work_by_slug[work.slug] = work
        if work.sc_root_uid:
            self.work_by_sc_uid[work.sc_root_uid] = work
        if work.toh_number:
            self.work_by_toh[work.toh_number] = work
        return work

    def _add_alias(self, work: Work, scheme: str, value: str) -> None:
        key = (scheme, value)
        if key in self.existing_aliases:
            return
        self.existing_aliases.add(key)
        self.work_by_alias[key] = work
        if not self.dry_run:
            self.session.add(WorkAlias(work=work, scheme=scheme, value=value))
        self.stats.aliases_created += 1

    def _add_witness(
        self,
        work: Work,
        text: BuddhistText,
        *,
        role: str,
        lang: str,
        canon: str | None,
        confidence: str,
        pass_name: str,
    ) -> bool:
        if text.id in self.assigned_text_ids:
            return False
        self.assigned_text_ids.add(text.id)
        if not self.dry_run:
            self.session.add(
                WorkWitness(
                    work=work,
                    text_id=text.id,
                    role=role,
                    lang=lang,
                    canon=canon,
                    confidence=confidence,
                )
            )
        self.stats.witnesses_created += 1
        self.stats.per_pass[pass_name] += 1
        return True

    def _slug(self, base: str, fallback: str) -> str:
        return make_unique_slug(base, self.taken_slugs, fallback=fallback)

    def _stamp_anchor(self, work: Work, cbeta_id: str) -> None:
        """Preserve a cross-pillar witness's canonical anchor on its Work, so the
        Work stays reachable by sc_root_uid / toh_number even when it was first
        created in pass 1 (Skt-title clustering). First anchor of each kind wins.
        """
        if cbeta_id.startswith("SC-") and not work.sc_root_uid:
            uid = sc_uid_from_cbeta_id(cbeta_id)
            work.sc_root_uid = uid
            self.work_by_sc_uid[uid] = work
            self._add_alias(work, "sc_uid", uid)
        elif cbeta_id.startswith("84K-toh") and not work.toh_number:
            toh = toh_number_from_cbeta_id(cbeta_id)
            work.toh_number = toh
            self.work_by_toh[toh] = work
            self._add_alias(work, "toh", toh)

    # -- passes --------------------------------------------------------------

    async def pass1_skt(self, texts: list[BuddhistText]) -> None:
        """Cluster every text carrying a title_sa by normalized Skt key.

        Over-broad clusters (size > max_skt_cluster, i.e. a generic class-level
        Skt title shared by many unrelated texts) are NOT merged; their texts
        fall through to singleton works in pass 4. The largest clusters are
        recorded on stats for --dry-run inspection.
        """
        groups: dict[str, list[BuddhistText]] = defaultdict(list)
        for t in texts:
            key = normalize_skt_title(t.title_sa)
            if not key:
                continue
            groups[key].append(t)

        # Record the largest clusters for human inspection (esp. under --dry-run).
        by_size = sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)
        self.stats.top_skt_clusters = [(k, len(g)) for k, g in by_size[:20] if len(g) > 1]

        for norm_key, group in groups.items():
            # Over-broad title → do NOT merge; leave for pass-4 singletons.
            if len(group) > self.max_skt_cluster:
                self.stats.skipped_skt_clusters.append((norm_key, len(group)))
                continue

            alias_key = ("skt_title", norm_key)
            work = self.work_by_alias.get(alias_key)
            if work is None:
                display = pick_display_title(group, norm_key)
                rep_skt = representative_skt_title(group)
                slug = self._slug(f"sk-{norm_key}", fallback="sk-work")
                work = self._new_work(
                    slug=slug,
                    title_primary=display[:500],
                    title_sa=(rep_skt[:500] if rep_skt else None),
                )
            self._add_alias(work, "skt_title", norm_key)

            for t in group:
                lang = t.lang or "lzh"
                added = self._add_witness(
                    work,
                    t,
                    role=role_from_lang(lang),
                    lang=lang,
                    canon=canon_from_cbeta_id(t.cbeta_id),
                    confidence="auto",
                    pass_name="pass1_skt",
                )
                # Keep cross-pillar Works reachable by their canonical IDs.
                if added and t.cbeta_id:
                    self._stamp_anchor(work, t.cbeta_id)

    async def pass2_sc(self, texts: list[BuddhistText]) -> None:
        for t in texts:
            if t.id in self.assigned_text_ids:
                continue
            if not t.cbeta_id or not t.cbeta_id.startswith("SC-"):
                continue
            uid = sc_uid_from_cbeta_id(t.cbeta_id)
            work = self.work_by_sc_uid.get(uid) or self.work_by_alias.get(("sc_uid", uid))
            if work is None:
                slug = self._slug(f"sc-{uid}", fallback="sc-work")
                work = self._new_work(
                    slug=slug,
                    title_primary=(t.title_zh or t.title_pi or t.title_en or uid)[:500],
                    title_pi=(t.title_pi[:500] if t.title_pi else None),
                    sc_root_uid=uid,
                )
            self._add_alias(work, "sc_uid", uid)
            self._add_witness(
                work,
                t,
                role="root",
                lang="pi",
                canon="pali",
                confidence="verified",
                pass_name="pass2_sc",
            )

    async def pass3_toh(self, texts: list[BuddhistText]) -> None:
        for t in texts:
            if t.id in self.assigned_text_ids:
                continue
            if not t.cbeta_id or not t.cbeta_id.startswith("84K-toh"):
                continue
            toh = toh_number_from_cbeta_id(t.cbeta_id)
            work = self.work_by_toh.get(toh) or self.work_by_alias.get(("toh", toh))
            if work is None:
                slug = self._slug(f"toh-{toh}", fallback="toh-work")
                work = self._new_work(
                    slug=slug,
                    title_primary=(t.title_zh or t.title_bo or t.title_en or f"Toh {toh}")[:500],
                    toh_number=toh,
                )
            self._add_alias(work, "toh", toh)
            self._add_witness(
                work,
                t,
                role="translation",
                lang="bo",
                canon="kangyur",
                confidence="verified",
                pass_name="pass3_toh",
            )

    async def pass4_singletons(self, texts: list[BuddhistText]) -> None:
        for t in texts:
            if t.id in self.assigned_text_ids:
                continue
            cbeta_id = t.cbeta_id or f"text-{t.id}"
            alias_key = ("cbeta_id", cbeta_id)
            work = self.work_by_alias.get(alias_key)
            if work is None:
                slug = self._slug(cbeta_id, fallback=f"text-{t.id}")
                work = self._new_work(
                    slug=slug,
                    title_primary=(t.title_zh or t.title_en or t.title_sa or cbeta_id)[:500],
                    title_sa=(t.title_sa[:500] if t.title_sa else None),
                )
            self._add_alias(work, "cbeta_id", cbeta_id)
            lang = t.lang or "lzh"
            self._add_witness(
                work,
                t,
                role=role_from_lang(lang),
                lang=lang,
                canon=canon_from_cbeta_id(t.cbeta_id),
                confidence="auto",
                pass_name="pass4_singleton",
            )

    async def run(self, texts: list[BuddhistText]) -> None:
        await self.pass1_skt(texts)
        await self.pass2_sc(texts)
        await self.pass3_toh(texts)
        await self.pass4_singletons(texts)


async def build(
    session: AsyncSession,
    *,
    dry_run: bool,
    limit: int | None = None,
    max_skt_cluster: int = MAX_SKT_CLUSTER_DEFAULT,
) -> BuildStats:
    """Load texts, run all four passes, commit (unless dry-run). Returns stats."""
    stats = BuildStats()
    builder = WorkBuilder(
        session, dry_run=dry_run, stats=stats, max_skt_cluster=max_skt_cluster
    )
    await builder.load_existing()

    stmt = select(BuddhistText).order_by(BuddhistText.id)
    if limit is not None:
        stmt = stmt.limit(limit)
    texts = list((await session.execute(stmt)).scalars().all())

    await builder.run(texts)

    if dry_run:
        await session.rollback()
    else:
        await session.commit()
    return stats


async def main_async(*, dry_run: bool, limit: int | None, max_skt_cluster: int) -> None:
    async with async_session() as session:
        stats = await build(
            session, dry_run=dry_run, limit=limit, max_skt_cluster=max_skt_cluster
        )
    if dry_run:
        print("(dry-run; no DB writes)")
    print(stats.summary())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dry-run", action="store_true", help="compute + log only; no DB writes"
    )
    ap.add_argument(
        "--limit", type=int, default=None, help="cap texts processed (testing)"
    )
    ap.add_argument(
        "--max-skt-cluster",
        type=int,
        default=MAX_SKT_CLUSTER_DEFAULT,
        help="Skt-title clusters larger than this are left as singletons "
        "(guards against over-broad generic titles)",
    )
    args = ap.parse_args()
    asyncio.run(
        main_async(
            dry_run=args.dry_run, limit=args.limit, max_skt_cluster=args.max_skt_cluster
        )
    )


if __name__ == "__main__":
    main()
