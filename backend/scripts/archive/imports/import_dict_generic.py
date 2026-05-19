"""
Generic dictionary import tool — supports multiple file formats.

Parses local dictionary files (TSV, CSV, JSON, MDict, StarDict) into
dictionary_entries via a pluggable DictParser architecture.

Usage:
    python scripts/import_dict_generic.py --format tsv --file dict.tsv --code mydict --name-zh "辞典名" --lang zh
    python scripts/import_dict_generic.py --format csv --file dict.csv --code mydict --name-zh "辞典名" --lang zh
    python scripts/import_dict_generic.py --format json --file dict.json --code mydict --name-zh "辞典名" --lang zh
    python scripts/import_dict_generic.py --format mdict --file dict.mdx --code mydict --name-zh "辞典名" --lang zh
    python scripts/import_dict_generic.py --format stardict --file dict.ifo --code mydict --name-zh "辞典名" --lang sa

    # Common options:
    --name-en "English Name"     # optional English name
    --limit 100                  # import first N entries only
    --encoding utf-8             # file encoding (default: utf-8, auto-detects BOM)
    --delimiter "\\t"            # field delimiter for TSV/CSV (default: auto from format)
    --headword-col 0             # column index for headword (TSV/CSV, default: 0)
    --reading-col 1              # column index for reading (TSV/CSV, default: none)
    --definition-col 1           # column index for definition (TSV/CSV, default: 1)
    --skip-rows 0                # skip N header rows (TSV/CSV, default: 0)
    --dry-run                    # parse and print stats without writing to DB

Note: This script is standalone and NOT registered in import_all.py.
      import_all.py orchestrates remote data sources that auto-download.
      This tool is for manual one-off imports from local files:
          python scripts/import_dict_generic.py --format tsv --file /path/to/dict.tsv ...
"""

import argparse
import asyncio
import csv
import io
import json
import os
import re
import struct
import sys
from abc import ABC, abstractmethod
from collections.abc import Generator
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.base_importer import BaseImporter
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class DictEntry(NamedTuple):
    """A single parsed dictionary entry."""

    headword: str
    reading: str | None
    definition: str
    external_id: str | None
    entry_data: dict | None


# ---------------------------------------------------------------------------
# HTML / markup stripping
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_SPACE_RE = re.compile(r"\s+")


def strip_html(text_: str) -> str:
    """Remove HTML/XML tags and collapse whitespace."""
    clean = _TAG_RE.sub(" ", text_)
    return _MULTI_SPACE_RE.sub(" ", clean).strip()


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

_BOM_MAP = {
    b"\xef\xbb\xbf": "utf-8-sig",
    b"\xff\xfe": "utf-16-le",
    b"\xfe\xff": "utf-16-be",
}


def detect_encoding(raw: bytes, fallback: str = "utf-8") -> str:
    """Detect encoding from BOM; fall back to *fallback*."""
    for bom, enc in _BOM_MAP.items():
        if raw.startswith(bom):
            return enc
    return fallback


def read_file_text(path: str, encoding: str = "utf-8") -> str:
    """Read a text file with encoding detection (BOM-aware)."""
    raw = Path(path).read_bytes()
    enc = detect_encoding(raw, fallback=encoding)
    # Try specified / detected encoding first, then common CJK encodings
    for try_enc in [enc, "utf-8", "gb18030", "big5", "euc-jp", "euc-kr"]:
        try:
            return raw.decode(try_enc)
        except (UnicodeDecodeError, LookupError):
            continue
    # Last resort: lossy UTF-8
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Base parser
# ---------------------------------------------------------------------------

class DictParser(ABC):
    """Base class for dictionary format parsers.

    Subclasses implement ``parse()`` which lazily yields ``DictEntry`` tuples.
    """

    def __init__(self, file_path: str, *, encoding: str = "utf-8", **kwargs):
        self.file_path = file_path
        self.encoding = encoding
        self.kwargs = kwargs

    @abstractmethod
    def parse(self) -> Generator[DictEntry, None, None]:
        """Yield ``DictEntry`` for every valid entry in the file."""
        ...


# ---------------------------------------------------------------------------
# TSV parser
# ---------------------------------------------------------------------------

class TSVParser(DictParser):
    """Parse tab-separated dictionary files.

    Expected layout (configurable via kwargs):
        headword<TAB>definition
        headword<TAB>reading<TAB>definition
    """

    def parse(self) -> Generator[DictEntry, None, None]:
        content = read_file_text(self.file_path, self.encoding)
        delimiter = self.kwargs.get("delimiter", "\t")
        headword_col = int(self.kwargs.get("headword_col", 0))
        reading_col = self.kwargs.get("reading_col")
        reading_col = int(reading_col) if reading_col is not None else None
        definition_col = int(self.kwargs.get("definition_col", 1))
        skip_rows = int(self.kwargs.get("skip_rows", 0))

        for i, line in enumerate(content.splitlines()):
            if i < skip_rows:
                continue
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split(delimiter)

            headword = parts[headword_col].strip() if headword_col < len(parts) else ""
            if not headword:
                continue

            definition = parts[definition_col].strip() if definition_col < len(parts) else ""
            if not definition:
                continue

            reading = None
            if reading_col is not None and reading_col < len(parts):
                reading = parts[reading_col].strip() or None

            yield DictEntry(
                headword=headword,
                reading=reading,
                definition=strip_html(definition),
                external_id=None,
                entry_data=None,
            )


# ---------------------------------------------------------------------------
# CSV parser
# ---------------------------------------------------------------------------

class CSVParser(DictParser):
    """Parse CSV dictionary files using Python's csv module."""

    def parse(self) -> Generator[DictEntry, None, None]:
        content = read_file_text(self.file_path, self.encoding)
        delimiter = self.kwargs.get("delimiter", ",")
        headword_col = int(self.kwargs.get("headword_col", 0))
        reading_col = self.kwargs.get("reading_col")
        reading_col = int(reading_col) if reading_col is not None else None
        definition_col = int(self.kwargs.get("definition_col", 1))
        skip_rows = int(self.kwargs.get("skip_rows", 0))

        reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        for i, row in enumerate(reader):
            if i < skip_rows:
                continue

            headword = row[headword_col].strip() if headword_col < len(row) else ""
            if not headword:
                continue

            definition = row[definition_col].strip() if definition_col < len(row) else ""
            if not definition:
                continue

            reading = None
            if reading_col is not None and reading_col < len(row):
                reading = row[reading_col].strip() or None

            # Collect remaining columns as entry_data
            entry_data = None
            extra = {}
            for idx, val in enumerate(row):
                if idx not in (headword_col, definition_col) and (reading_col is None or idx != reading_col):
                    val = val.strip()
                    if val:
                        extra[f"col_{idx}"] = val
            if extra:
                entry_data = extra

            yield DictEntry(
                headword=headword,
                reading=reading,
                definition=strip_html(definition),
                external_id=None,
                entry_data=entry_data,
            )


# ---------------------------------------------------------------------------
# JSON parser
# ---------------------------------------------------------------------------

class JSONParser(DictParser):
    """Parse JSON dictionary files.

    Accepts two layouts:
    1. Array of objects: [{"headword": "...", "definition": "...", ...}, ...]
    2. Object mapping headword → definition: {"word": "meaning", ...}

    For layout 1, recognised keys: headword/word/term, definition/meaning/gloss,
    reading/pronunciation/pinyin, external_id/id.
    """

    _HW_KEYS = ("headword", "word", "term", "entry", "key", "lemma")
    _DEF_KEYS = ("definition", "meaning", "gloss", "translation", "english", "value")
    _RD_KEYS = ("reading", "pronunciation", "pinyin", "phonetic", "kana")
    _ID_KEYS = ("external_id", "id", "entry_id")

    def _pick(self, obj: dict, candidates: tuple[str, ...]) -> str | None:
        for k in candidates:
            if obj.get(k):
                return str(obj[k]).strip()
        return None

    def parse(self) -> Generator[DictEntry, None, None]:
        content = read_file_text(self.file_path, self.encoding)
        data = json.loads(content)

        if isinstance(data, dict):
            # Layout 2: {headword: definition, ...}
            for hw, defn in data.items():
                hw = str(hw).strip()
                defn = str(defn).strip() if defn else ""
                if hw and defn:
                    yield DictEntry(
                        headword=hw,
                        reading=None,
                        definition=strip_html(defn),
                        external_id=None,
                        entry_data=None,
                    )
        elif isinstance(data, list):
            # Layout 1: [{headword, definition, ...}, ...]
            for item in data:
                if not isinstance(item, dict):
                    continue
                hw = self._pick(item, self._HW_KEYS)
                defn = self._pick(item, self._DEF_KEYS)
                if not hw or not defn:
                    continue

                reading = self._pick(item, self._RD_KEYS)
                ext_id = self._pick(item, self._ID_KEYS)

                # Everything else goes into entry_data
                known = set(self._HW_KEYS + self._DEF_KEYS + self._RD_KEYS + self._ID_KEYS)
                extra = {k: v for k, v in item.items() if k not in known and v}
                entry_data = extra if extra else None

                yield DictEntry(
                    headword=hw,
                    reading=reading,
                    definition=strip_html(defn),
                    external_id=ext_id,
                    entry_data=entry_data,
                )
        else:
            raise ValueError("JSON root must be an array or an object")


# ---------------------------------------------------------------------------
# MDict parser (.mdx)
# ---------------------------------------------------------------------------

class MdictParser(DictParser):
    """Parse MDict .mdx files.

    Requires one of:
    - ``mdict_utils``  (pip install mdict-utils)
    - ``readmdict``    (pip install readmdict)
    """

    def parse(self) -> Generator[DictEntry, None, None]:
        # Try mdict_utils first (newer, maintained)
        try:
            from mdict_utils import MDict  # type: ignore[import-untyped]

            mdx = MDict(self.file_path)
            items = mdx.items()
            for key_bytes, val_bytes in items:
                hw = key_bytes.decode("utf-8", errors="replace").strip() if isinstance(key_bytes, bytes) else str(key_bytes).strip()
                defn = val_bytes.decode("utf-8", errors="replace").strip() if isinstance(val_bytes, bytes) else str(val_bytes).strip()
                if not hw or not defn:
                    continue
                yield DictEntry(
                    headword=hw,
                    reading=None,
                    definition=strip_html(defn),
                    external_id=None,
                    entry_data=None,
                )
            return
        except ImportError:
            pass

        # Fall back to readmdict
        try:
            from readmdict import MDX  # type: ignore[import-untyped]

            mdx = MDX(self.file_path)
            items = mdx.items()
            for key_bytes, val_bytes in items:
                hw = key_bytes.decode("utf-8", errors="replace").strip() if isinstance(key_bytes, bytes) else str(key_bytes).strip()
                defn = val_bytes.decode("utf-8", errors="replace").strip() if isinstance(val_bytes, bytes) else str(val_bytes).strip()
                if not hw or not defn:
                    continue
                yield DictEntry(
                    headword=hw,
                    reading=None,
                    definition=strip_html(defn),
                    external_id=None,
                    entry_data=None,
                )
            return
        except ImportError:
            pass

        raise ImportError(
            "MDict support requires 'mdict-utils' or 'readmdict'. "
            "Install with: pip install mdict-utils   OR   pip install readmdict"
        )


# ---------------------------------------------------------------------------
# StarDict parser (.ifo / .idx / .dict[.dz])
# ---------------------------------------------------------------------------

class StarDictParser(DictParser):
    """Parse StarDict dictionary files.

    Pass the .ifo file as ``file_path``. The parser locates the companion
    .idx and .dict (or .dict.dz) in the same directory.

    Tries ``pystardict`` first; falls back to a built-in reader.
    """

    def parse(self) -> Generator[DictEntry, None, None]:
        # Try pystardict library first
        try:
            from pystardict import Dictionary  # type: ignore[import-untyped]

            sd = Dictionary(self.file_path)
            for word in sd:
                defn = sd[word]
                if isinstance(defn, bytes):
                    defn = defn.decode("utf-8", errors="replace")
                defn = defn.strip()
                if word and defn:
                    yield DictEntry(
                        headword=word.strip(),
                        reading=None,
                        definition=strip_html(defn),
                        external_id=None,
                        entry_data=None,
                    )
            return
        except ImportError:
            pass

        # Built-in StarDict reader
        yield from self._builtin_parse()

    def _builtin_parse(self) -> Generator[DictEntry, None, None]:
        base = Path(self.file_path)
        stem = base.with_suffix("")  # strip .ifo

        # Locate idx
        idx_path = stem.with_suffix(".idx")
        if not idx_path.exists():
            raise FileNotFoundError(f"StarDict .idx not found: {idx_path}")

        # Locate dict (possibly gzipped)
        dict_path = stem.with_suffix(".dict")
        dict_dz_path = Path(str(dict_path) + ".dz")

        if dict_dz_path.exists():
            import gzip

            with gzip.open(dict_dz_path, "rb") as gz:
                dict_data = gz.read()
        elif dict_path.exists():
            dict_data = dict_path.read_bytes()
        else:
            raise FileNotFoundError(f"StarDict .dict or .dict.dz not found alongside {base}")

        # Parse .ifo to get idxoffsetbits (default 32)
        ifo_text = base.read_text(encoding="utf-8", errors="replace")
        offset_bits = 32
        for line in ifo_text.splitlines():
            if line.startswith("idxoffsetbits="):
                offset_bits = int(line.split("=", 1)[1].strip())

        # Parse .idx: null-terminated word + offset (4 or 8 bytes) + size (4 bytes)
        idx_data = idx_path.read_bytes()
        pos = 0
        offset_fmt = ">I" if offset_bits == 32 else ">Q"
        offset_size = 4 if offset_bits == 32 else 8

        while pos < len(idx_data):
            # Find null terminator for word
            null_pos = idx_data.index(b"\x00", pos)
            word = idx_data[pos:null_pos].decode("utf-8", errors="replace")
            pos = null_pos + 1

            offset = struct.unpack(offset_fmt, idx_data[pos : pos + offset_size])[0]
            pos += offset_size
            size = struct.unpack(">I", idx_data[pos : pos + 4])[0]
            pos += 4

            defn_bytes = dict_data[offset : offset + size]
            defn = defn_bytes.decode("utf-8", errors="replace").strip()

            if word and defn:
                yield DictEntry(
                    headword=word.strip(),
                    reading=None,
                    definition=strip_html(defn),
                    external_id=None,
                    entry_data=None,
                )


# ---------------------------------------------------------------------------
# Parser registry
# ---------------------------------------------------------------------------

PARSERS: dict[str, type[DictParser]] = {
    "tsv": TSVParser,
    "csv": CSVParser,
    "json": JSONParser,
    "mdict": MdictParser,
    "stardict": StarDictParser,
}


# ---------------------------------------------------------------------------
# Importer (uses BaseImporter for DB/logging)
# ---------------------------------------------------------------------------

class GenericDictImporter(BaseImporter):
    """Import dictionary entries from a local file using a pluggable parser."""

    RATE_LIMIT_DELAY = 0  # local file, no network

    def __init__(
        self,
        *,
        parser: DictParser,
        code: str,
        name_zh: str,
        name_en: str = "",
        lang: str = "zh",
        limit: int = 0,
        dry_run: bool = False,
    ):
        self.SOURCE_CODE = code
        self.SOURCE_NAME_ZH = name_zh
        self.SOURCE_NAME_EN = name_en or name_zh
        super().__init__()

        self.parser = parser
        self.lang = lang
        self.limit = limit
        self.dry_run = dry_run

    async def run_import(self):
        print(f"  Parsing {self.parser.file_path} (format: {type(self.parser).__name__})...")

        imported = 0
        skipped = 0
        seen_ids: set[str] = set()

        if self.dry_run:
            # Dry run: just count entries
            for _entry in self.parser.parse():
                imported += 1
                if self.limit > 0 and imported >= self.limit:
                    break
            print(f"  [DRY RUN] Would import {imported} entries.")
            self.stats.texts_created = imported
            return

        async with self.session_factory() as session:
            source = await self.ensure_source(session)

            for entry in self.parser.parse():
                if not entry.headword or not entry.definition:
                    skipped += 1
                    continue

                # Build a unique external_id
                ext_id = entry.external_id or f"{self.SOURCE_CODE}-{entry.headword}"
                if ext_id in seen_ids:
                    ext_id = f"{ext_id}-{imported}"
                seen_ids.add(ext_id)
                ext_id = ext_id[:200]

                entry_data_json = json.dumps(entry.entry_data, ensure_ascii=False) if entry.entry_data else None

                await session.execute(
                    text("""
                        INSERT INTO dictionary_entries
                            (headword, reading, definition, source_id, lang, external_id, entry_data)
                        VALUES (:headword, :reading, :definition, :source_id, :lang, :external_id,
                                CAST(:entry_data AS jsonb))
                        ON CONFLICT ON CONSTRAINT uq_dict_entry_source_external DO UPDATE SET
                            headword = EXCLUDED.headword,
                            reading = EXCLUDED.reading,
                            definition = EXCLUDED.definition,
                            entry_data = EXCLUDED.entry_data
                    """),
                    {
                        "headword": entry.headword[:500],
                        "reading": (entry.reading or "")[:500] or None,
                        "definition": entry.definition,
                        "source_id": source.id,
                        "lang": self.lang,
                        "external_id": ext_id,
                        "entry_data": entry_data_json,
                    },
                )
                imported += 1

                if imported % 5000 == 0:
                    await session.commit()
                    print(f"    ... {imported} entries processed")

                if self.limit > 0 and imported >= self.limit:
                    break

            await session.commit()

        self.stats.texts_created = imported
        self.stats.skipped = skipped
        print(f"  Imported {imported} entries, skipped {skipped}.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generic dictionary importer — supports TSV, CSV, JSON, MDict, StarDict",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/import_dict_generic.py --format tsv --file dict.tsv --code mydict --name-zh "辞典名" --lang zh
  python scripts/import_dict_generic.py --format mdict --file dict.mdx --code mydict --name-zh "辞典名" --lang zh
  python scripts/import_dict_generic.py --format stardict --file dict.ifo --code mydict --name-zh "辞典名" --lang sa
  python scripts/import_dict_generic.py --format json --file dict.json --code mydict --name-zh "辞典名" --lang zh
  python scripts/import_dict_generic.py --format csv --file dict.csv --code mydict --name-zh "辞典名" --lang zh

Column mapping (TSV/CSV only):
  python scripts/import_dict_generic.py --format tsv --file dict.tsv \\
      --headword-col 0 --reading-col 2 --definition-col 3 --skip-rows 1 \\
      --code mydict --name-zh "辞典名" --lang zh
        """,
    )

    # Required
    p.add_argument("--format", "-f", required=True, choices=list(PARSERS.keys()), help="Dictionary file format")
    p.add_argument("--file", "-F", required=True, help="Path to dictionary file")
    p.add_argument("--code", "-c", required=True, help="Data source code (e.g. 'soothill')")
    p.add_argument("--name-zh", required=True, help="Chinese name of the dictionary")

    # Optional metadata
    p.add_argument("--name-en", default="", help="English name of the dictionary")
    p.add_argument("--lang", default="zh", help="Headword language code (default: zh)")
    p.add_argument("--limit", type=int, default=0, help="Import at most N entries (0 = all)")
    p.add_argument("--dry-run", action="store_true", help="Parse only, don't write to DB")

    # File parsing options
    p.add_argument("--encoding", default="utf-8", help="File encoding (default: utf-8, BOM auto-detected)")
    p.add_argument("--delimiter", default=None, help="Field delimiter for TSV/CSV (default: auto)")
    p.add_argument("--headword-col", type=int, default=0, help="Headword column index (TSV/CSV, default: 0)")
    p.add_argument("--reading-col", type=int, default=None, help="Reading column index (TSV/CSV, default: none)")
    p.add_argument("--definition-col", type=int, default=1, help="Definition column index (TSV/CSV, default: 1)")
    p.add_argument("--skip-rows", type=int, default=0, help="Skip N header rows (TSV/CSV, default: 0)")

    return p


async def main():
    args = build_parser().parse_args()

    # Validate file exists
    file_path = os.path.abspath(args.file)
    if not os.path.isfile(file_path):
        print(f"Error: file not found: {file_path}")
        sys.exit(1)

    # Build parser kwargs
    parser_kwargs: dict = {
        "encoding": args.encoding,
        "headword_col": args.headword_col,
        "definition_col": args.definition_col,
        "skip_rows": args.skip_rows,
    }
    if args.reading_col is not None:
        parser_kwargs["reading_col"] = args.reading_col
    if args.delimiter is not None:
        parser_kwargs["delimiter"] = args.delimiter

    # Instantiate parser
    parser_cls = PARSERS[args.format]
    parser = parser_cls(file_path, **parser_kwargs)

    # Instantiate importer
    importer = GenericDictImporter(
        parser=parser,
        code=args.code,
        name_zh=args.name_zh,
        name_en=args.name_en,
        lang=args.lang,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
