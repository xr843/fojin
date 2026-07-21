"""Decode numeric character references left as literal text in dictionary_entries.

Prod 2026-07-21: 2,463 headwords and 7,663 definitions read like ``&#X4E98;以``
instead of ``亘以``. Affected sources are 一切經音義（慧琳音義） (2,255 headwords /
6,986 definitions) and 續一切經音義（希麟） (208 / 676) — two phonological
dictionaries dense in rare characters, which buddhaspace.org serves as numeric
character references.

Cause: ``scripts/archive/imports/import_buddhaspace.py::_strip_html`` decoded five
named entities by hand and no numeric ones. Because its ``&amp;`` → ``&`` pass runs
first, a source ``&amp;#X4E98;`` is turned INTO the literal ``&#X4E98;`` and then
left there. That importer is fixed in the same change; this script repairs the rows
already in the database.

Why it matters beyond cosmetics: each junk headword is a /dict/ page crawlers index,
and every crawl costs a reverse-index lookup against a 276MB TOASTed column.

Usage:
    python -m scripts.fix_dict_html_entities              # dry run (default)
    python -m scripts.fix_dict_html_entities --write      # apply
    python -m scripts.fix_dict_html_entities --limit 20   # sample a few rows
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys

# app.database is imported inside main() on purpose: importing it builds the
# async engine, and decode_numeric_entities() is a pure function that its tests
# must be able to import without standing up a database.

# Matches ``&#1234;`` and ``&#x4E98;`` / ``&#X4E98;``. Named entities are
# deliberately NOT matched — see decode_numeric_entities().
_NUMERIC_REF = re.compile(r"&#(?:[xX]([0-9A-Fa-f]+)|([0-9]+));")


def _is_safe_codepoint(cp: int) -> bool:
    """Reject anything Postgres text cannot hold or that is not a scalar value.

    Surrogates (U+D800–DFFF) are not valid on their own, U+0000 cannot be stored
    in a Postgres text column at all, and C0 controls would be invisible damage.
    """
    if cp > 0x10FFFF:
        return False
    if 0xD800 <= cp <= 0xDFFF:
        return False
    if cp < 0x20:
        return False
    return True


def decode_numeric_entities(s: str) -> str:
    """Replace numeric character references with the characters they denote.

    Only numeric references are touched. Named entities (``&amp;``, ``&nbsp;``…)
    are left verbatim so this can never rewrite a legitimate ``&`` sitting in a
    definition body — this is a repair migration, not a general text cleaner.

    Unsafe or unrepresentable code points are left as-is rather than replaced
    with a placeholder, so anything skipped stays findable by the same
    ``LIKE '%&#%'`` query that found it.
    """
    if not s:
        return s

    def _repl(m: re.Match[str]) -> str:
        hex_digits, dec_digits = m.group(1), m.group(2)
        try:
            cp = int(hex_digits, 16) if hex_digits is not None else int(dec_digits, 10)
        except ValueError:  # pragma: no cover - regex already constrains the digits
            return m.group(0)
        if not _is_safe_codepoint(cp):
            return m.group(0)
        return chr(cp)

    return _NUMERIC_REF.sub(_repl, s)


SELECT_SQL = """
    SELECT id, headword, definition
    FROM dictionary_entries
    WHERE headword LIKE '%&#%' OR definition LIKE '%&#%'
    ORDER BY id
"""

UPDATE_SQL = """
    UPDATE dictionary_entries
    SET headword = :headword, definition = :definition
    WHERE id = :id
"""


async def main() -> int:
    from sqlalchemy import text

    from app.database import async_session

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--write",
        action="store_true",
        help="apply the changes; without it the script only reports (default: dry run)",
    )
    ap.add_argument("--limit", type=int, default=0, help="only consider the first N rows")
    ap.add_argument("--samples", type=int, default=15, help="how many before/after pairs to print")
    args = ap.parse_args()

    async with async_session() as session:
        rows = (await session.execute(text(SELECT_SQL))).all()
        if args.limit:
            rows = rows[: args.limit]

        planned = []
        skipped = []
        for row_id, headword, definition in rows:
            new_head = decode_numeric_entities(headword or "")
            new_def = decode_numeric_entities(definition or "")
            if new_head == (headword or "") and new_def == (definition or ""):
                # Nothing decodable — a leftover unsafe reference, or a stray '&#'
                # that is not a character reference at all.
                skipped.append((row_id, headword))
                continue
            planned.append(
                {
                    "id": row_id,
                    "headword": new_head,
                    "definition": new_def,
                    "_old_head": headword,
                }
            )

        head_changes = sum(1 for p in planned if p["headword"] != p["_old_head"])

        print(f"匹配行数        : {len(rows)}")
        print(f"可修复          : {len(planned)}  (其中 headword 变化 {head_changes})")
        print(f"跳过(无可解码)  : {len(skipped)}")

        if planned:
            print("\n--- headword 修改样本 (修前 -> 修后) ---")
            shown = 0
            for p in planned:
                if p["headword"] == p["_old_head"]:
                    continue
                print(f"  {p['_old_head']!r}  ->  {p['headword']!r}")
                shown += 1
                if shown >= args.samples:
                    break

        if skipped:
            print("\n--- 跳过样本 ---")
            for row_id, hw in skipped[:5]:
                print(f"  id={row_id} headword={hw!r}")

        if not args.write:
            print("\n[dry-run] 未写入任何数据。确认无误后加 --write 执行。")
            return 0

        for p in planned:
            p.pop("_old_head")
        await session.execute(text(UPDATE_SQL), planned)
        await session.commit()
        print(f"\n[write] 已更新 {len(planned)} 行。")

        left = (
            await session.execute(
                text(
                    "SELECT count(*) FROM dictionary_entries "
                    "WHERE headword LIKE '%&#%' OR definition LIKE '%&#%'"
                )
            )
        ).scalar()
        print(f"[verify] 仍含 '&#' 的行: {left}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
