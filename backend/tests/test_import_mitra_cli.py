"""Unit tests for the CLI / idempotency logic in scripts/import_mitra_alignments.py.

Follows the test_archive_importers.py pattern: load the script module from
scripts/ via importlib; no live Postgres is touched.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))


def load_script():
    spec = importlib.util.spec_from_file_location(
        "import_mitra_alignments_for_test", BACKEND_ROOT / "scripts/import_mitra_alignments.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mod = load_script()


def _args(**overrides):
    base = {"all": False, "taisho": None, "mitra_dir": "/nonexistent"}
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# Target resolution (_resolve_targets) — default MUST stay the pilot list
# ---------------------------------------------------------------------------


def test_default_scope_is_exactly_the_pilot_list():
    assert mod._resolve_targets(_args()) == mod.PILOT_TAISHO
    assert mod.PILOT_TAISHO == [
        "T0099",
        "T0310",
        "T1146",
        "T1424",
        "T1509",
        "T1579",
        "T1636",
        "T1736",
        "T2016",
        "T2122",
    ]


def test_taisho_ids_are_parsed_from_comma_list_with_whitespace_and_empties():
    args = _args(taisho=" T0099, T0310 ,,T0945,")
    assert mod._resolve_targets(args) == ["T0099", "T0310", "T0945"]


def test_all_scope_derives_sorted_taisho_ids_from_tsv_filenames(tmp_path):
    (tmp_path / "T04n0192_D0001.tsv").touch()
    (tmp_path / "T25n1509_T08n0223.tsv").touch()
    (tmp_path / "notes.txt").touch()  # non-TSV ignored
    args = _args(all=True, mitra_dir=str(tmp_path))
    assert mod._resolve_targets(args) == ["T0192", "T0223", "T1509"]


def test_all_takes_precedence_over_taisho_list(tmp_path):
    (tmp_path / "T04n0192_D0001.tsv").touch()
    args = _args(all=True, taisho="T0099", mitra_dir=str(tmp_path))
    assert mod._resolve_targets(args) == ["T0192"]


# ---------------------------------------------------------------------------
# CLI flags (_build_parser)
# ---------------------------------------------------------------------------


def test_taisho_ids_flag_is_an_alias_of_taisho():
    parser = mod._build_parser()
    args = parser.parse_args(["--mitra-dir", "/x", "--taisho-ids", "T0099,T0310"])
    assert args.taisho == "T0099,T0310"
    legacy = parser.parse_args(["--mitra-dir", "/x", "--taisho", "T0099,T0310"])
    assert legacy.taisho == args.taisho


def test_parser_defaults_preserve_pilot_reproducibility():
    args = mod._build_parser().parse_args(["--mitra-dir", "/x"])
    assert args.taisho is None
    assert args.all is False
    assert args.dry_run is False
    assert args.skip_existing is False  # default remains wipe+re-import
    assert args.log_every == 25
    assert mod._resolve_targets(args) == mod.PILOT_TAISHO


# ---------------------------------------------------------------------------
# Skip-already-imported idempotency (_partition_imported)
# ---------------------------------------------------------------------------


def test_partition_imported_splits_and_preserves_order():
    targets = ["T0099", "T0310", "T1509", "T2122"]
    todo, skipped = mod._partition_imported(targets, {"T0310", "T2122"})
    assert todo == ["T0099", "T1509"]
    assert skipped == ["T0310", "T2122"]


def test_partition_imported_nothing_imported():
    todo, skipped = mod._partition_imported(["T0099", "T0310"], set())
    assert todo == ["T0099", "T0310"]
    assert skipped == []


def test_partition_imported_everything_imported():
    todo, skipped = mod._partition_imported(["T0099"], {"T0099", "T0310"})
    assert todo == []
    assert skipped == ["T0099"]


# ---------------------------------------------------------------------------
# In-run duplicate guard (_dedup_key / _dedup_rows)
# ---------------------------------------------------------------------------


def _row(**overrides):
    base = {
        "zh_segment": "T04n0192_002:0010c23_13",
        "foreign_segment": "D0001_012",
        "zh_text": "如是我聞",
        "foreign_text": "evaṃ mayā śrutam",
        "mitra_file": "a.tsv",
    }
    base.update(overrides)
    return base


def test_dedup_drops_exact_duplicates_keeping_first():
    rows = [_row(), _row(mitra_file="b.tsv")]  # same pair from two TSV files
    unique, dropped = mod._dedup_rows(rows)
    assert dropped == 1
    assert len(unique) == 1
    assert unique[0]["mitra_file"] == "a.tsv"  # first occurrence wins


def test_dedup_key_is_location_specific():
    # The same formulaic sentence at two Taishō line refs is NOT a duplicate.
    rows = [_row(), _row(zh_segment="T04n0192_003:0021a05_02")]
    unique, dropped = mod._dedup_rows(rows)
    assert dropped == 0
    assert len(unique) == 2


def test_dedup_key_distinguishes_different_foreign_sides():
    rows = [_row(), _row(foreign_segment="D0001_013", foreign_text="anyat")]
    unique, dropped = mod._dedup_rows(rows)
    assert dropped == 0
    assert len(unique) == 2


def test_dedup_key_excludes_mitra_file():
    assert mod._dedup_key(_row(mitra_file="a.tsv")) == mod._dedup_key(_row(mitra_file="b.tsv"))
