"""Tests for eval/build_alignment_gold.py — gold-set candidate construction.

Pure-logic tests over synthetic fixtures: record mapping from the three
stores' shapes, shifted/cross_text negative construction, stratified
sampling, and determinism under --seed. The --from-export CLI path is
exercised end-to-end with tmp files; --from-db (thin SQL) runs only on prod.
"""

import json
import random

import pytest
from eval.build_alignment_gold import (
    build_from_export,
    export_row_to_gold,
    main,
    make_cross_text_negatives,
    make_shifted_negatives,
    mitra_row_to_gold,
    pair_kind_from_langs,
    positive_pair_keys,
    relation_row_to_gold,
    stratified_sample,
)


def _export_row(row_id=1, lang_src="pi", lang_tgt="lzh", verified=False):
    """A row in scripts/export_alignment_dataset.py's output format."""
    return {
        "id": row_id,
        "lang_src": lang_src,
        "lang_tgt": lang_tgt,
        "src": {"text_id": 273, "canonical_id": "SC-mn10", "title": None, "juan": 1, "chunk_index": 3},
        "tgt": {"text_id": 2, "canonical_id": "T0026", "title": "中阿含經", "juan": 24, "chunk_index": 5},
        "segment_src": "kāye kāyānupassī viharati",
        "segment_tgt": "观身如身念处",
        "confidence": 0.92,
        "method": "embed_llm",
        "verified": verified,
    }


# --- pair_kind_from_langs ----------------------------------------------------

def test_pair_kind_direction_normalized_zh_first():
    assert pair_kind_from_langs("lzh", "pi") == "zh-pi"
    assert pair_kind_from_langs("pi", "lzh") == "zh-pi"
    assert pair_kind_from_langs("bo", "lzh") == "zh-bo"


def test_pair_kind_folds_aliases():
    assert pair_kind_from_langs("zho", "tib") == "zh-bo"
    assert pair_kind_from_langs("skt", "zh") == "zh-sa"
    assert pair_kind_from_langs("eng", "lzh") == "zh-en"


def test_pair_kind_rejects_non_zh_and_unknown_pairs():
    assert pair_kind_from_langs("pi", "bo") is None   # no Chinese side
    assert pair_kind_from_langs("lzh", "lzh") is None  # same language
    assert pair_kind_from_langs("lzh", "fr") is None   # unknown code
    assert pair_kind_from_langs(None, "lzh") is None


# --- store-row → gold mapping --------------------------------------------------

def test_export_row_maps_all_fields():
    record = export_row_to_gold(_export_row())
    assert record["record_id"] == "ap-1"
    assert record["source"] == "alignment_pairs"
    assert record["source_row_id"] == 1
    assert record["granularity"] == "chunk"
    assert record["pair_kind"] == "zh-pi"
    assert record["side_a"] == {
        "text_id": 273, "juan_num": 1, "chunk_index": 3, "lang": "pi",
        "text": "kāye kāyānupassī viharati",
    }
    assert record["side_b"]["text_id"] == 2
    assert record["side_b"]["lang"] == "zh"
    assert record["label"] is True
    assert record["negative_kind"] is None
    assert "confidence=0.92" in record["note"]


def test_export_row_label_source_tracks_human_verification():
    assert export_row_to_gold(_export_row(verified=False))["label_source"] == "seed_verified"
    assert export_row_to_gold(_export_row(verified=True))["label_source"] == "human"


def test_export_row_non_zh_pair_returns_none():
    assert export_row_to_gold(_export_row(lang_src="pi", lang_tgt="bo")) is None


def test_mitra_row_foreign_side_is_inline_text():
    record = mitra_row_to_gold({
        "id": 88001, "text_id": 6513, "taisho_id": "T0262", "juan_num": 2,
        "chunk_index": 14, "zh_text": "诸法从本来", "foreign_lang": "sa",
        "foreign_text": "ādibuddhāḥ sarvadharmāḥ", "match_scope": "juan",
    })
    assert record["record_id"] == "ma-88001"
    assert record["source"] == "mitra_alignments"
    assert record["pair_kind"] == "zh-sa"
    assert record["side_a"]["text_id"] == 6513
    assert record["side_b"] == {"text": "ādibuddhāḥ sarvadharmāḥ", "lang": "sa"}
    assert "text_id" not in record["side_b"]
    assert record["label_source"] == "seed_verified"  # mitra confidence is an import flag


def test_relation_row_is_sutta_granularity():
    record = relation_row_to_gold({
        "id": 501, "text_a_id": 2207, "text_b_id": 3,
        "lang_a": "pi", "lang_b": "lzh", "source": "suttacentral",
    })
    assert record["record_id"] == "tr-501"
    assert record["granularity"] == "sutta"
    assert record["side_a"] == {"text_id": 2207, "lang": "pi"}
    assert record["side_b"] == {"text_id": 3, "lang": "zh"}


# --- shifted negatives ---------------------------------------------------------

def _positive(record_id="ap-1", b_chunk=5):
    return export_row_to_gold({**_export_row(), "id": record_id.split("-")[1]}) | {
        "record_id": record_id,
        "side_b": {"text_id": 2, "juan_num": 24, "chunk_index": b_chunk, "lang": "zh"},
    }


def test_shifted_negative_offsets_side_b_and_keeps_identity():
    positive = _positive()
    negatives = make_shifted_negatives(
        [positive], chunk_exists=lambda t, j, c: True,
        rng=random.Random(1), per_positive=1,
    )
    assert len(negatives) == 1
    neg = negatives[0]
    assert neg["label"] is False
    assert neg["negative_kind"] == "shifted"
    assert neg["label_source"] == "seed_verified"  # constructed → needs human pass
    assert neg["source_row_id"] is None
    assert neg["side_a"] == positive["side_a"]
    offset = neg["side_b"]["chunk_index"] - positive["side_b"]["chunk_index"]
    assert offset in (-2, -1, 1, 2) and offset != 0
    assert neg["record_id"] == f"neg-shifted-ap-1{'+' if offset > 0 else ''}{offset}"
    assert neg["pair_kind"] == positive["pair_kind"]


def test_shifted_negative_respects_chunk_existence():
    positive = _positive(b_chunk=0)
    # Only chunk 1 exists next to 0 (negative indexes are skipped anyway,
    # -2/-1 are < 0, and +2 "doesn't exist" in this fixture).
    negatives = make_shifted_negatives(
        [positive], chunk_exists=lambda t, j, c: c == 1,
        rng=random.Random(7), per_positive=4,
    )
    assert [n["side_b"]["chunk_index"] for n in negatives] == [1]


def test_shifted_negative_never_lands_on_a_known_positive():
    p1 = _positive("ap-1", b_chunk=5)
    p2 = _positive("ap-2", b_chunk=6)  # chunk 6 IS a true positive for the same side_a
    known = positive_pair_keys([p1, p2])
    negatives = make_shifted_negatives(
        [p1], chunk_exists=lambda t, j, c: True,
        rng=random.Random(3), known_pairs=known, per_positive=4,
    )
    landed = {n["side_b"]["chunk_index"] for n in negatives}
    assert 6 not in landed  # +1 collides with p2 and must be excluded
    assert landed <= {3, 4, 7}


def test_shifted_negatives_skip_sutta_and_inline_rows():
    sutta = relation_row_to_gold({
        "id": 501, "text_a_id": 2207, "text_b_id": 3,
        "lang_a": "pi", "lang_b": "lzh", "source": None,
    })
    mitra = mitra_row_to_gold({
        "id": 1, "text_id": 5, "taisho_id": "T0001", "juan_num": 1,
        "chunk_index": 2, "zh_text": "x", "foreign_lang": "bo",
        "foreign_text": "y", "match_scope": "juan",
    })  # side_b is inline text — nothing to shift
    negatives = make_shifted_negatives(
        [sutta, mitra], chunk_exists=lambda t, j, c: True,
        rng=random.Random(1), per_positive=2,
    )
    assert negatives == []


def test_shifted_negatives_deterministic_under_seed():
    positives = [_positive(f"ap-{i}", b_chunk=10 + i) for i in range(1, 6)]
    make = lambda seed: make_shifted_negatives(  # noqa: E731
        positives, chunk_exists=lambda t, j, c: True, rng=random.Random(seed), per_positive=1,
    )
    assert make(42) == make(42)
    assert make(42) != make(43)  # offset choice actually depends on the rng


# --- cross_text negatives --------------------------------------------------------

def _pool():
    return [
        {"text_id": 99, "juan_num": 1, "chunk_index": 0, "lang": "lzh", "text": "无关文本甲"},
        {"text_id": 98, "juan_num": 2, "chunk_index": 4, "lang": "lzh", "text": "无关文本乙"},
        {"text_id": 97, "juan_num": 1, "chunk_index": 1, "lang": "bo", "text": "wrong language"},
        {"text_id": 2, "juan_num": 9, "chunk_index": 9, "lang": "lzh", "text": "same text as side_b"},
    ]


def test_cross_text_negative_picks_unrelated_same_language_chunk():
    positive = _positive()  # side_a text 273 (pi), side_b text 2 (zh)
    negatives = make_cross_text_negatives([positive], _pool(), random.Random(5), per_positive=2)
    assert len(negatives) == 2
    for neg in negatives:
        assert neg["negative_kind"] == "cross_text"
        assert neg["label"] is False
        assert neg["side_a"] == positive["side_a"]
        assert neg["side_b"]["text_id"] in {99, 98}  # never 2 (own text) nor 97 (wrong lang)
        assert neg["side_b"]["lang"] == "zh"
        assert neg["pair_kind"] == positive["pair_kind"]


def test_cross_text_negative_excludes_related_texts():
    positive = _positive()
    related = {(273, 99)}  # text 99 is a known parallel of side_a's text
    negatives = make_cross_text_negatives(
        [positive], _pool(), random.Random(5), related_text_pairs=related, per_positive=4,
    )
    assert {n["side_b"]["text_id"] for n in negatives} == {98}


def test_cross_text_negative_excludes_reverse_direction_relation():
    positive = _positive()
    related = {(99, 273)}  # same relation, stored in the other direction
    negatives = make_cross_text_negatives(
        [positive], _pool(), random.Random(5), related_text_pairs=related, per_positive=4,
    )
    assert 99 not in {n["side_b"]["text_id"] for n in negatives}


def test_cross_text_negative_empty_pool_yields_nothing():
    assert make_cross_text_negatives([_positive()], [], random.Random(1)) == []


def test_cross_text_deterministic_under_seed():
    positives = [_positive(f"ap-{i}") for i in range(1, 4)]
    make = lambda seed: make_cross_text_negatives(  # noqa: E731
        positives, _pool(), random.Random(seed), per_positive=1,
    )
    assert make(42) == make(42)


# --- stratified_sample -----------------------------------------------------------

def _kind_record(i, kind):
    return {"record_id": f"r{kind}{i}", "pair_kind": kind}


def test_stratified_caps_each_kind_independently():
    records = [_kind_record(i, "zh-pi") for i in range(10)] + [_kind_record(i, "zh-bo") for i in range(2)]
    sampled = stratified_sample(records, per_kind=5, rng=random.Random(0))
    kinds = [r["pair_kind"] for r in sampled]
    assert kinds.count("zh-pi") == 5
    assert kinds.count("zh-bo") == 2  # under the cap → all kept


def test_stratified_none_keeps_everything():
    records = [_kind_record(i, "zh-pi") for i in range(10)]
    assert len(stratified_sample(records, per_kind=None, rng=random.Random(0))) == 10


def test_stratified_deterministic_under_seed():
    records = [_kind_record(i, "zh-pi") for i in range(50)]
    a = stratified_sample(records, per_kind=10, rng=random.Random(42))
    b = stratified_sample(records, per_kind=10, rng=random.Random(42))
    assert a == b


# --- --from-export end-to-end ------------------------------------------------------

@pytest.fixture
def export_file(tmp_path):
    path = tmp_path / "export.jsonl"
    rows = [
        _export_row(1, "pi", "lzh"),
        _export_row(2, "lzh", "bo", verified=True),
        _export_row(3, "pi", "bo"),  # non zh-X → skipped
        _export_row(4, "lzh", "sa"),
    ]
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return path


def test_build_from_export_maps_validates_and_shuffles(export_file):
    records = build_from_export(export_file, per_kind=None, seed=42)
    assert {r["record_id"] for r in records} == {"ap-1", "ap-2", "ap-4"}
    assert all(r["label"] is True for r in records)
    by_id = {r["record_id"]: r for r in records}
    assert by_id["ap-2"]["label_source"] == "human"
    assert by_id["ap-1"]["label_source"] == "seed_verified"


def test_build_from_export_deterministic_under_seed(export_file):
    assert build_from_export(export_file, None, 42) == build_from_export(export_file, None, 42)
    ordered_a = [r["record_id"] for r in build_from_export(export_file, None, 1)]
    ordered_b = [r["record_id"] for r in build_from_export(export_file, None, 2)]
    assert set(ordered_a) == set(ordered_b)  # same content, order may differ per seed


def test_cli_from_export_writes_jsonl(export_file, tmp_path, capsys):
    out = tmp_path / "gold" / "candidates.jsonl"
    main(["--from-export", str(export_file), "--out", str(out), "--seed", "7"])
    lines = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 3
    assert all(line["source"] == "alignment_pairs" for line in lines)
    stdout = capsys.readouterr().out
    assert "skipped 1" in stdout  # the pi-bo row
    assert "CANDIDATES" in stdout  # human-review warning printed


def test_sample_gold_file_is_valid():
    """The shipped sample must satisfy the format it documents."""
    from pathlib import Path

    from eval.alignment_metrics import validate_gold_record

    sample = Path(__file__).resolve().parents[1] / "eval" / "alignment_gold.sample.jsonl"
    records = [json.loads(line) for line in sample.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records) == 10
    for record in records:
        assert validate_gold_record(record) == [], record["record_id"]
        assert "SYNTHETIC" in record["note"]
    # Every enum value is demonstrated at least once.
    assert {r["pair_kind"] for r in records} == {"zh-pi", "zh-bo", "zh-sa", "zh-en"}
    assert {r["granularity"] for r in records} == {"chunk", "sutta"}
    assert {r["label_source"] for r in records} == {"human", "seed_verified"}
    assert {r["source"] for r in records} == {"alignment_pairs", "mitra_alignments", "text_relations"}
    assert {r["negative_kind"] for r in records if not r["label"]} == {
        "shifted", "cross_text", "near_neighbor", None,
    }
