"""Import MITRA cross-lingual parallels into the mitra_alignments table.

Source: github.com/dharmamitra/mitra-parallel (Nehrdich & Keutzer,
arXiv:2601.06400), CC BY-SA 4.0. Sentence-level Sanskrit/Tibetan ↔ Buddhist
Chinese alignments, TSV per source-pair, Chinese side keyed by Taishō line id
(e.g. T04n0192_002:0010c23_13).

Pipeline (per Taishō text, to bound memory on a small VPS):
  1. Load that text's fojin chunks (text_embeddings.chunk_text) and build a
     per-juan normalized concatenation + chunk-offset index.
  2. Walk the MITRA TSV files that involve this text, take each Chinese
     sentence, normalize (strip whitespace/punct/latin/digits), and locate it
     verbatim inside the juan -> the fojin chunk_index that contains it.
     (Quality gate A: only sentences that localize are imported. Pilot measured
     ~98% localize; the rest are edition/variant-char mismatches.)
  3. Wipe this text's existing rows (idempotent re-run) and bulk insert.

The MITRA-E (9B) semantic gate is a separate later enhancement; this importer
ships the substring gate only.

Usage (inside backend container, DB reachable):
    python scripts/import_mitra_alignments.py --mitra-dir /tmp/mitra-tsv
    python scripts/import_mitra_alignments.py --mitra-dir /tmp/mitra-tsv --all \
        --skip-existing --log-every 25
    python scripts/import_mitra_alignments.py --mitra-dir /tmp/mitra-tsv \
        --taisho-ids T0262,T0945 --dry-run

With no scope flag the run covers exactly the 10 pilot texts (PILOT_TAISHO),
so historical re-runs stay reproducible. Idempotency: per text the importer
wipes and re-inserts atomically (one transaction); --skip-existing instead
skips any text that already has rows — use it to resume an interrupted --all
run and to protect backfilled mitra_e_score values, which a wipe would erase.
"""
from __future__ import annotations

import argparse
import asyncio
import bisect
import glob
import os
import re
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings

# The 10 texts validated end-to-end in the pilot (default scope).
PILOT_TAISHO = [
    "T0099", "T0310", "T1146", "T1424", "T1509",
    "T1579", "T1636", "T1736", "T2016", "T2122",
]

_PUNCT = re.compile(r"[\s　，。、；：！？·「」『』（）()．,0-9A-Za-z\-—…〈〉《》【】\[\]]+")
# BMP + CJK Ext-A + Ext-B, so all-rare-character / gaiji-heavy Chinese sentences
# still register as Chinese.
_CJK = re.compile(r"[㐀-䶿一-鿿\U00020000-\U0002a6df]")
_TIB = re.compile(r"[ༀ-࿿]")
_ZH_SEG = re.compile(r"^T\d+n\d+")

# Localization tuning.
_SEP = "\x00"          # chunk separator in the per-juan concat (never appears in normalized text)
_MIN_LEN = 4           # skip MITRA sentences shorter than this (normalized length)
_CROSS_JUAN_MIN = 12   # only allow the cross-juan fallback for sentences at least this long

INSERT = sql_text(
    """
    INSERT INTO mitra_alignments
        (text_id, taisho_id, juan_num, chunk_index, zh_text, foreign_lang,
         foreign_text, zh_segment, foreign_segment, mitra_file, match_scope)
    VALUES
        (:text_id, :taisho_id, :juan_num, :chunk_index, :zh_text, :foreign_lang,
         :foreign_text, :zh_segment, :foreign_segment, :mitra_file, :match_scope)
    """
)


def _norm(s: str) -> str:
    return _PUNCT.sub("", s)


def _taisho_of(seg: str) -> str | None:
    m = re.match(r"^T\d+n0*(\d+)", seg)
    return f"T{int(m.group(1)):04d}" if m else None


def _juan_of(seg: str) -> int | None:
    m = re.match(r"^T\d+n\d+[a-zA-Z]*_(\d+)", seg)
    return int(m.group(1)) if m else None


async def _load_chunks(conn, taisho: str):
    """Return (text_id, tj_index, t_index) for one Taishō text, or (None, ...)."""
    rows = (
        await conn.execute(
            sql_text(
                """
                SELECT te.text_id, te.juan_num, te.chunk_index, te.chunk_text
                FROM text_embeddings te
                JOIN buddhist_texts bt ON bt.id = te.text_id
                WHERE bt.taisho_id = :t
                ORDER BY te.juan_num, te.chunk_index
                """
            ),
            {"t": taisho},
        )
    ).fetchall()
    if not rows:
        return None, {}, []

    text_id = rows[0][0]
    per_juan: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for _tid, juan, cidx, ctext in rows:
        per_juan[juan].append((cidx, _norm(ctext or "")))

    tj_index: dict[int, tuple[str, list[int], list[int]]] = {}
    t_index: list[tuple[int, str, list[int], list[int]]] = []
    for juan, chunks in per_juan.items():
        chunks.sort()
        offs: list[int] = []
        idxs: list[int] = []
        parts: list[str] = []
        cur = 0
        for cidx, nt in chunks:
            if not nt:
                # Skip chunks that normalize to empty (all punctuation/markup):
                # they can't contain a match and would create duplicate offsets
                # that make the bisect lookup ambiguous.
                continue
            offs.append(cur)
            idxs.append(cidx)
            parts.append(nt)
            cur += len(nt) + len(_SEP)
        if not parts:
            continue
        # Join with a sentinel so a sentence that straddles a chunk boundary is
        # NOT found across the seam (it would otherwise be mis-attributed to the
        # chunk where its first char lands, or match spuriously at the join).
        concat = _SEP.join(parts)
        tj_index[juan] = (concat, offs, idxs)
        t_index.append((juan, concat, offs, idxs))
    return text_id, tj_index, t_index


def _locate(ns: str, juan: int | None, tj_index, t_index):
    """Find the fojin chunk containing the normalized sentence. Returns
    (chunk_index, juan, scope) where scope is 'juan' | 'taisho' | 'none'.

    The cross-juan ('taisho') fallback only fires for sufficiently long
    sentences AND only when the match is unique across juans. Short formulaic
    phrases (爾時世尊, 如是我聞) recur in many juans; taking the first hit would
    anchor them to an arbitrary wrong juan, so an ambiguous match is dropped.
    """
    hit = tj_index.get(juan) if juan is not None else None
    if hit:
        concat, offs, idxs = hit
        p = concat.find(ns)
        if p >= 0:
            return idxs[bisect.bisect_right(offs, p) - 1], juan, "juan"
    if len(ns) >= _CROSS_JUAN_MIN:
        match: tuple[int, int] | None = None
        for j, concat, offs, idxs in t_index:
            if j == juan:
                continue
            p = concat.find(ns)
            if p >= 0:
                if match is not None:
                    return None, None, "none"  # found in >1 juan → ambiguous, drop
                match = (idxs[bisect.bisect_right(offs, p) - 1], j)
        if match is not None:
            return match[0], match[1], "taisho"
    return None, None, "none"


def _dedup_key(row: dict) -> tuple[str, str, str, str]:
    """Script-level uniqueness key for one alignment row.

    The table has no unique constraint (bulk-load table; the DB-level guard is
    only the per-text wipe), so this is the strongest natural key available:
    the Taishō line ref + foreign segment id + both text sides. zh_segment is
    location-specific (e.g. T04n0192_002:0010c23_13), so a formulaic sentence
    repeated at two places in a text is NOT collapsed — only true duplicates
    (the same alignment appearing in more than one MITRA TSV file) are.
    """
    return (row["zh_segment"], row["foreign_segment"], row["zh_text"], row["foreign_text"])


def _dedup_rows(rows: list[dict]) -> tuple[list[dict], int]:
    """Drop exact duplicate rows within one text's import, keeping the first
    occurrence (deterministic). Returns (unique_rows, dropped_count)."""
    seen: set[tuple[str, str, str, str]] = set()
    out: list[dict] = []
    for row in rows:
        key = _dedup_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out, len(rows) - len(out)


def _partition_imported(targets: list[str], imported: set[str]) -> tuple[list[str], list[str]]:
    """Split targets into (todo, skipped) preserving order.

    The idempotency key is the Taishō id: a text is "imported" when its
    text_id already has any mitra_alignments rows. Safe because _import_one
    writes a text's delete+insert atomically in one transaction, so a text
    either has its full row set or nothing.
    """
    todo = [t for t in targets if t not in imported]
    skipped = [t for t in targets if t in imported]
    return todo, skipped


def _pairs_for(tsv_dir: str, taisho: str):
    """Yield (mitra_file, zh_seg, zh, fo_seg, fo) for one Taishō text."""
    files = [
        f
        for f in glob.glob(os.path.join(tsv_dir, "*.tsv"))
        if any(_taisho_of(t) == taisho for t in re.findall(r"T\d+n\d+", os.path.basename(f)))
    ]
    for fp in files:
        base = os.path.basename(fp)
        with open(fp, encoding="utf-8") as fh:
            for line in fh:
                c = line.rstrip("\n").split("\t")
                if len(c) < 4:
                    continue
                if _ZH_SEG.match(c[0]):
                    zh_seg, zh, fo_seg, fo = c[0], c[1], c[2], c[3]
                elif _ZH_SEG.match(c[2]):
                    zh_seg, zh, fo_seg, fo = c[2], c[3], c[0], c[1]
                else:
                    continue
                if _taisho_of(zh_seg) != taisho or not _CJK.search(zh):
                    continue
                yield base, zh_seg, zh, fo_seg, fo


async def _import_one(conn, taisho: str, tsv_dir: str, dry: bool) -> tuple[int, int]:
    text_id, tj_index, t_index = await _load_chunks(conn, taisho)
    if text_id is None:
        print(f"  {taisho}: not in fojin (skip)")
        return 0, 0

    # Localize first (pure CPU), building the full row set BEFORE any write, so
    # the DELETE's row locks are held only for the quick delete+insert window,
    # not during the localization loop. In dry-run we only count (no rows held).
    cand = loc = 0
    rows: list[dict] = []
    for base, zh_seg, zh, fo_seg, fo in _pairs_for(tsv_dir, taisho):
        ns = _norm(zh)
        if len(ns) < _MIN_LEN:
            continue
        cand += 1
        ci, fj, scope = _locate(ns, _juan_of(zh_seg), tj_index, t_index)
        if ci is None:
            continue
        loc += 1
        if dry:
            continue
        # Tibetan text is stored in Tibetan script; Sanskrit in IAST/Devanagari.
        # Script detection is ground truth here (verified on the pilot corpus:
        # 119,067 Tibetan rows all carry Tibetan script). Do NOT classify by the
        # segment id's Derge "D" token — it is embedded mid-id (e.g. K10D0095)
        # and false-positives on Sanskrit ids.
        folang = "bo" if _TIB.search(fo) else "sa"
        rows.append(
            {
                "text_id": text_id,
                "taisho_id": taisho,
                "juan_num": fj,
                "chunk_index": ci,
                "zh_text": zh,
                "foreign_lang": folang,
                "foreign_text": fo,
                "zh_segment": zh_seg[:80],
                "foreign_segment": fo_seg[:80],
                "mitra_file": base[:160],
                "match_scope": scope,
            }
        )

    if not dry:
        rows, dropped = _dedup_rows(rows)
        if dropped:
            print(f"  {taisho}: dropped {dropped} exact duplicate row(s)")
        await conn.execute(
            sql_text("DELETE FROM mitra_alignments WHERE text_id = :tid"), {"tid": text_id}
        )
        for i in range(0, len(rows), 5000):
            await conn.execute(INSERT, rows[i : i + 5000])
        await conn.commit()

    pct = loc * 100 // max(cand, 1)
    print(f"  {taisho} (text_id={text_id}): cand={cand} localized={loc} ({pct}%)")
    return cand, loc


def _resolve_targets(args) -> list[str]:
    if args.all:
        seen = {
            _taisho_of(t)
            for f in glob.glob(os.path.join(args.mitra_dir, "*.tsv"))
            for t in re.findall(r"T\d+n\d+", os.path.basename(f))
        }
        return sorted(t for t in seen if t)
    if args.taisho:
        return [x.strip() for x in args.taisho.split(",") if x.strip()]
    return PILOT_TAISHO


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mitra-dir", required=True, help="path to mitra-parallel/tsv")
    ap.add_argument(
        "--taisho",
        "--taisho-ids",
        dest="taisho",
        help="comma-separated Taishō ids, e.g. T0099,T0310 (default: pilot 10)",
    )
    ap.add_argument("--all", action="store_true", help="all Chinese-bearing texts present in fojin")
    ap.add_argument("--dry-run", action="store_true", help="localize + report, no writes")
    ap.add_argument(
        "--skip-existing",
        action="store_true",
        help="skip texts that already have mitra_alignments rows (resume an "
        "interrupted run; protects backfilled mitra_e_score, which the "
        "default wipe+re-import would erase)",
    )
    ap.add_argument(
        "--log-every",
        type=int,
        default=25,
        help="print cumulative progress every N texts (default 25; 0 disables)",
    )
    return ap


async def main() -> int:
    args = _build_parser().parse_args()

    if not os.path.isdir(args.mitra_dir):
        print(f"ERROR: --mitra-dir not found: {args.mitra_dir}")
        return 1

    targets = _resolve_targets(args)
    print(f"targets: {len(targets)} Taishō text(s); dry_run={args.dry_run}")

    t0 = time.time()
    tot_c = tot_l = 0
    # Dedicated NullPool engine + a single connection held for the whole run.
    # The app's pooled session re-checks-out a connection after every commit;
    # on fojin's connection-starved Postgres (app pool 30+90 can exceed
    # max_connections, shared with umami) that re-checkout fails mid-run with
    # "too many clients". One long-lived connection only needs a free slot once,
    # at startup, and adds exactly one connection of pressure.
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    failed: list[str] = []
    try:
        async with engine.connect() as conn:
            if args.skip_existing:
                imported = {
                    row[0]
                    for row in (
                        await conn.execute(
                            sql_text(
                                """
                                SELECT DISTINCT bt.taisho_id
                                FROM mitra_alignments ma
                                JOIN buddhist_texts bt ON bt.id = ma.text_id
                                """
                            )
                        )
                    ).fetchall()
                }
                targets, already = _partition_imported(targets, imported)
                print(f"skip-existing: {len(already)} already imported, {len(targets)} to do")

            for idx, taisho in enumerate(targets, 1):
                try:
                    c, lcount = await _import_one(conn, taisho, args.mitra_dir, args.dry_run)
                    tot_c += c
                    tot_l += lcount
                except Exception as e:
                    # One bad text must not abort the whole run. Roll back the
                    # aborted transaction so the shared connection stays usable.
                    await conn.rollback()
                    failed.append(taisho)
                    print(f"  {taisho}: FAILED ({type(e).__name__}: {e})")
                if args.log_every and idx % args.log_every == 0:
                    elapsed = time.time() - t0
                    rate = tot_l / elapsed if elapsed > 0 else 0.0
                    eta = (len(targets) - idx) * elapsed / idx
                    print(
                        f"progress: {idx}/{len(targets)} texts, localized={tot_l} rows, "
                        f"{rate:.0f} rows/s, elapsed={elapsed:.0f}s, eta={eta:.0f}s"
                    )
    finally:
        await engine.dispose()
    pct = tot_l * 100 // max(tot_c, 1)
    print(f"TOTAL: cand={tot_c} localized={tot_l} ({pct}%) in {time.time() - t0:.1f}s")
    if failed:
        tail = " …" if len(failed) > 30 else ""
        print(f"FAILED ({len(failed)}): {', '.join(failed[:30])}{tail}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
