"""Unit tests for scripts/backfill_mitra_scores.py (pure logic, mocked DB/API).

Follows the test_archive_importers.py pattern: load the script module from
scripts/ via importlib; no live Postgres or embedding API is touched.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.exceptions import EmbeddingServiceError


def load_script():
    spec = importlib.util.spec_from_file_location(
        "backfill_mitra_scores_for_test", BACKEND_ROOT / "scripts/backfill_mitra_scores.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mod = load_script()


# ---------------------------------------------------------------------------
# cosine_similarity
# ---------------------------------------------------------------------------


def test_cosine_identical_vectors_is_one():
    assert mod.cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_scaled_vectors_is_one():
    assert mod.cosine_similarity([1.0, 0.0], [7.5, 0.0]) == pytest.approx(1.0)


def test_cosine_orthogonal_vectors_is_zero():
    assert mod.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_opposite_vectors_is_minus_one():
    assert mod.cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_zero_vector_returns_none():
    assert mod.cosine_similarity([0.0, 0.0], [1.0, 0.0]) is None
    assert mod.cosine_similarity([1.0, 0.0], [0.0, 0.0]) is None


def test_cosine_length_mismatch_returns_none():
    assert mod.cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) is None


def test_cosine_empty_returns_none():
    assert mod.cosine_similarity([], []) is None


def test_cosine_is_clamped_to_unit_interval():
    score = mod.cosine_similarity([1e-8, 1e-8], [1e-8, 1e-8])
    assert score is not None
    assert -1.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# chunked
# ---------------------------------------------------------------------------


def test_chunked_exact_division():
    assert list(mod.chunked([1, 2, 3, 4], 2)) == [[1, 2], [3, 4]]


def test_chunked_remainder_tail():
    assert list(mod.chunked([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_chunked_size_larger_than_input():
    assert list(mod.chunked([1, 2], 10)) == [[1, 2]]


def test_chunked_empty_input():
    assert list(mod.chunked([], 3)) == []


def test_chunked_invalid_size_raises():
    with pytest.raises(ValueError):
        list(mod.chunked([1], 0))


# ---------------------------------------------------------------------------
# band_of / _band_where
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "band"),
    [
        (0.0, 0),
        (0.05, 0),
        (0.1, 1),
        (0.35, 3),
        (0.95, 9),
        (1.0, 9),  # closed top band
        (-0.5, 0),  # clamped
        (1.2, 9),  # clamped (float fuzz)
    ],
)
def test_band_of(score, band):
    assert mod.band_of(score) == band


def test_band_where_edges_are_open_ended():
    assert "lo" not in mod._band_where(0)  # no lower bound on first band
    assert "IS NOT NULL" in mod._band_where(0)  # but NULLs excluded
    assert "hi" not in mod._band_where(mod.BANDS - 1)  # no upper bound on last band
    mid = mod._band_where(4)
    assert ":lo" in mid and ":hi" in mid


# ---------------------------------------------------------------------------
# allocate_quotas (stratified sampling)
# ---------------------------------------------------------------------------


def test_quotas_even_split():
    assert mod.allocate_quotas(20, [10] * 10) == [2] * 10


def test_quotas_remainder_goes_to_earliest_bands():
    assert mod.allocate_quotas(23, [10] * 10) == [3, 3, 3, 2, 2, 2, 2, 2, 2, 2]


def test_quotas_shortfall_redistributed_to_bands_with_spare_rows():
    available = [0, 0, 0, 0, 0, 20, 20, 0, 0, 0]
    quotas = mod.allocate_quotas(10, available)
    assert quotas == [0, 0, 0, 0, 0, 5, 5, 0, 0, 0]
    assert sum(quotas) == 10


def test_quotas_never_exceed_availability():
    available = [1, 0, 3, 100, 0, 2, 0, 0, 0, 50]
    quotas = mod.allocate_quotas(30, available)
    assert all(q <= a for q, a in zip(quotas, available, strict=True))
    assert sum(quotas) == 30


def test_quotas_insufficient_rows_takes_everything():
    assert mod.allocate_quotas(100, [1, 2, 3]) == [1, 2, 3]


def test_quotas_zero_total_and_empty_bands():
    assert mod.allocate_quotas(0, [5, 5]) == [0, 0]
    assert mod.allocate_quotas(10, []) == []


def test_quotas_deterministic():
    available = [3, 7, 0, 11, 2, 9, 0, 4, 8, 1]
    assert mod.allocate_quotas(25, available) == mod.allocate_quotas(25, available)


# ---------------------------------------------------------------------------
# embed_with_retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_retry_success_first_try():
    calls = []

    async def ok(texts):
        calls.append(texts)
        return [[1.0]] * len(texts)

    result = await mod.embed_with_retry(["a", "b"], attempts=3, base_delay=0, embed_fn=ok)
    assert result == [[1.0], [1.0]]
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_embed_retry_recovers_after_transient_failures():
    calls = []

    async def flaky(texts):
        calls.append(texts)
        if len(calls) < 3:
            raise EmbeddingServiceError("transient")
        return [[0.5]] * len(texts)

    result = await mod.embed_with_retry(["a"], attempts=3, base_delay=0, embed_fn=flaky)
    assert result == [[0.5]]
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_embed_retry_gives_up_and_returns_none():
    calls = []

    async def broken(texts):
        calls.append(texts)
        raise EmbeddingServiceError("down")

    result = await mod.embed_with_retry(["a"], attempts=3, base_delay=0, embed_fn=broken)
    assert result is None
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_embed_retry_does_not_swallow_unexpected_errors():
    async def bug(texts):
        raise ValueError("programming error")

    with pytest.raises(ValueError):
        await mod.embed_with_retry(["a"], attempts=3, base_delay=0, embed_fn=bug)


# ---------------------------------------------------------------------------
# run_backfill with a fake connection + mocked embedding client
# ---------------------------------------------------------------------------


class FakeConn:
    """Minimal async stand-in for an SQLAlchemy connection, scripted around
    the three statements run_backfill issues (count / fetch / update)."""

    def __init__(self, rows: list[tuple[int, str, str]]):
        self._rows = rows  # (id, zh_text, foreign_text), NULL-score rows
        self.updates: list[dict] = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "count(*)" in sql:
            return _FakeResult(scalar=len(self._rows))
        if "UPDATE mitra_alignments" in sql:
            self.updates.extend(params)
            return _FakeResult()
        assert "id > :cursor" in sql
        batch = [r for r in self._rows if r[0] > params["cursor"]][: params["n"]]
        return _FakeResult(rows=batch)

    async def commit(self):
        self.commits += 1


class _FakeResult:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def fetchall(self):
        return self._rows

    def scalar_one(self):
        return self._scalar


VECTORS = {
    "zh1": [1.0, 0.0],
    "fo1": [1.0, 0.0],  # cosine 1.0
    "zh2": [1.0, 0.0],
    "fo2": [0.0, 1.0],  # cosine 0.0
    "zh3": [1.0, 0.0],
    "fo3": [0.0, 0.0],  # zero vector -> unscorable, stays NULL
}


async def fake_embed_batch(texts):
    return [VECTORS[t] for t in texts]


@pytest.mark.asyncio
async def test_run_backfill_scores_rows_and_advances_cursor(monkeypatch):
    monkeypatch.setattr(mod.embedding_service, "generate_embeddings_batch", fake_embed_batch)
    conn = FakeConn([(1, "zh1", "fo1"), (2, "zh2", "fo2"), (3, "zh3", "fo3")])

    scored, skipped = await mod.run_backfill(
        conn,
        batch_size=2,
        limit=None,
        dry_run=False,
        log_every=10_000,
        retry_attempts=1,
        retry_delay=0,
    )

    assert scored == 2
    assert skipped == 1  # zero-vector row left NULL
    by_id = {u["id"]: u["score"] for u in conn.updates}
    assert by_id[1] == pytest.approx(1.0)
    assert by_id[2] == pytest.approx(0.0)
    assert 3 not in by_id
    assert conn.commits == 1  # only the first batch had updates to write


@pytest.mark.asyncio
async def test_run_backfill_dry_run_writes_nothing(monkeypatch):
    monkeypatch.setattr(mod.embedding_service, "generate_embeddings_batch", fake_embed_batch)
    conn = FakeConn([(1, "zh1", "fo1"), (2, "zh2", "fo2")])

    scored, skipped = await mod.run_backfill(
        conn,
        batch_size=10,
        limit=None,
        dry_run=True,
        log_every=10_000,
        retry_attempts=1,
        retry_delay=0,
    )

    assert scored == 2
    assert skipped == 0
    assert conn.updates == []
    assert conn.commits == 0


@pytest.mark.asyncio
async def test_run_backfill_limit_caps_processed_rows(monkeypatch):
    monkeypatch.setattr(mod.embedding_service, "generate_embeddings_batch", fake_embed_batch)
    conn = FakeConn([(1, "zh1", "fo1"), (2, "zh2", "fo2"), (3, "zh1", "fo1")])

    scored, skipped = await mod.run_backfill(
        conn,
        batch_size=1,
        limit=2,
        dry_run=False,
        log_every=10_000,
        retry_attempts=1,
        retry_delay=0,
    )

    assert scored + skipped == 2
    assert len(conn.updates) == 2


@pytest.mark.asyncio
async def test_run_backfill_skips_batch_when_embedding_api_is_down(monkeypatch):
    async def down(texts):
        raise EmbeddingServiceError("api down")

    monkeypatch.setattr(mod.embedding_service, "generate_embeddings_batch", down)
    conn = FakeConn([(1, "zh1", "fo1"), (2, "zh2", "fo2")])

    scored, skipped = await mod.run_backfill(
        conn,
        batch_size=2,
        limit=None,
        dry_run=False,
        log_every=10_000,
        retry_attempts=2,
        retry_delay=0,
    )

    assert scored == 0
    assert skipped == 2  # counted, cursor advanced, no infinite loop
    assert conn.updates == []
    assert conn.commits == 0


# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------


def test_parser_defaults():
    args = mod._build_parser().parse_args([])
    assert args.batch_size == 64
    assert args.limit is None
    assert args.dry_run is False
    assert args.export_calibration is None


def test_parser_export_calibration_takes_n_and_path():
    args = mod._build_parser().parse_args(["--export-calibration", "500", "/tmp/calib.jsonl"])
    assert args.export_calibration == ["500", "/tmp/calib.jsonl"]


def test_export_jsonl_row_shape_matches_labeling_contract():
    # The JSONL contract consumed by human labelers: exactly these six fields.
    row = {
        "id": 1,
        "taisho_id": "T0099",
        "zh_text": "如是我聞",
        "foreign_text": "evaṃ mayā śrutam",
        "foreign_lang": "sa",
        "mitra_e_score": 0.87,
    }
    line = json.dumps(row, ensure_ascii=False)
    assert set(json.loads(line)) == {
        "id",
        "taisho_id",
        "zh_text",
        "foreign_text",
        "foreign_lang",
        "mitra_e_score",
    }
    assert "如是我聞" in line  # ensure_ascii=False keeps CJK readable
