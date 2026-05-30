"""Tests for scripts/build_works.py.

Two layers:

  * Pure-logic unit tests — no DB, no fixtures. Always run.
  * One integration test against an in-memory SQLite async DB created with
    ``Base.metadata.create_all``. This needs ``aiosqlite`` (a dev dep) but no
    external services (PG/ES/Redis), matching the conftest philosophy. If
    ``aiosqlite`` is unavailable the integration test is skipped, not failed.

Run:  python -m pytest tests/test_build_works.py -q
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Make ``scripts`` importable (repo layout has no package for it).
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_ROOT))
sys.path.insert(0, str(_BACKEND_ROOT / "scripts"))

import build_works as bw

# ---------------------------------------------------------------------------
# Pure logic — normalization
# ---------------------------------------------------------------------------


def test_normalize_merges_case_space_diacritics():
    a = bw.normalize_skt_title("Vajracchedikā Prajñāpāramitā")
    b = bw.normalize_skt_title("vajracchedika  prajnaparamita")
    c = bw.normalize_skt_title("  VAJRACCHEDIKĀ\tPRAJÑĀPĀRAMITĀ  ")
    assert a == b == c
    assert a == "vajracchedika prajnaparamita"


def test_normalize_empty_inputs():
    assert bw.normalize_skt_title(None) == ""
    assert bw.normalize_skt_title("") == ""
    assert bw.normalize_skt_title("   \t \n ") == ""


def test_normalize_collapses_internal_whitespace():
    assert bw.normalize_skt_title("a\t\n  b   c") == "a b c"


# ---------------------------------------------------------------------------
# Pure logic — canon from prefix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cbeta_id,expected",
    [
        ("T0251", "taisho"),
        ("X1551", "xuzang"),
        ("SC-an10.1", "pali"),
        ("SC-dn1", "pali"),
        ("84K-toh2", "kangyur"),
        ("GRETIL-foo", "gretil"),
        ("VRI-bar", "pali"),
        ("ZZZ-unknown", None),
        ("", None),
        (None, None),
    ],
)
def test_canon_from_cbeta_id(cbeta_id, expected):
    assert bw.canon_from_cbeta_id(cbeta_id) == expected


def test_canon_sc_prefix_beats_t_prefix():
    # SC- must be checked before the bare "T"/"X" rule (it is not, but it does
    # not start with T anyway — guard the ordering against future edits).
    assert bw.canon_from_cbeta_id("SC-thig1.1") == "pali"
    assert bw.canon_from_cbeta_id("84K-toh100") == "kangyur"


# ---------------------------------------------------------------------------
# Pure logic — role
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "lang,expected",
    [("sa", "root"), ("pi", "root"), ("lzh", "translation"), ("bo", "translation"), (None, "translation")],
)
def test_role_from_lang(lang, expected):
    assert bw.role_from_lang(lang) == expected


# ---------------------------------------------------------------------------
# Pure logic — slug sanitize + uniqueness
# ---------------------------------------------------------------------------


def test_sanitize_slug_base():
    assert bw.sanitize_slug_base("Vajracchedikā Prajñā") == "vajracchedika-prajna"
    assert bw.sanitize_slug_base("T0251") == "t0251"
    assert bw.sanitize_slug_base("SC-an10.1") == "sc-an10-1"
    assert bw.sanitize_slug_base("  --weird__name!!  ") == "weird-name"
    assert bw.sanitize_slug_base("妙法蓮華經") == ""  # no ascii survives


def test_sanitize_slug_only_allowed_chars():
    import re

    for raw in ["Héllo Wörld", "T0251", "84K-toh2", "a/b\\c.d", "ṣaḍ-akṣarī"]:
        out = bw.sanitize_slug_base(raw)
        assert out == "" or re.fullmatch(r"[a-z0-9-]+", out), out


def test_make_unique_slug_collisions():
    taken: set[str] = set()
    s1 = bw.make_unique_slug("sk-foo", taken)
    s2 = bw.make_unique_slug("sk-foo", taken)
    s3 = bw.make_unique_slug("sk-foo", taken)
    assert s1 == "sk-foo"
    assert s2 == "sk-foo-2"
    assert s3 == "sk-foo-3"
    assert len(taken) == 3


def test_make_unique_slug_empty_uses_fallback():
    taken: set[str] = set()
    s = bw.make_unique_slug("妙法蓮華經", taken, fallback="text-7")
    assert s == "text-7"


def test_make_unique_slug_truncates_to_200():
    taken: set[str] = set()
    s = bw.make_unique_slug("a" * 300, taken)
    assert len(s) <= 200


# ---------------------------------------------------------------------------
# Pure logic — display title / toh / sc extraction
# ---------------------------------------------------------------------------


class _FakeText:
    def __init__(self, **kw):
        self.title_zh = kw.get("title_zh")
        self.title_sa = kw.get("title_sa")
        self.title_en = kw.get("title_en")
        self.title_bo = kw.get("title_bo")
        self.title_pi = kw.get("title_pi")


def test_pick_display_title_prefers_zh():
    g = [_FakeText(title_sa="Vajracchedikā"), _FakeText(title_zh="金剛經", title_sa="Vajracchedikā")]
    assert bw.pick_display_title(g, "vajracchedika") == "金剛經"


def test_pick_display_title_falls_back_to_skt_then_key():
    g = [_FakeText(title_sa="Vajracchedikā")]
    assert bw.pick_display_title(g, "vajracchedika") == "Vajracchedikā"
    g2 = [_FakeText()]
    assert bw.pick_display_title(g2, "somekey") == "somekey"


def test_toh_and_sc_extraction():
    assert bw.toh_number_from_cbeta_id("84K-toh2") == "2"
    assert bw.toh_number_from_cbeta_id("84K-toh100") == "100"
    assert bw.sc_uid_from_cbeta_id("SC-an10.1") == "an10.1"
    assert bw.sc_uid_from_cbeta_id("SC-dn1") == "dn1"


# ---------------------------------------------------------------------------
# Integration — in-memory SQLite async DB (skips if aiosqlite unavailable)
# ---------------------------------------------------------------------------

_HAS_AIOSQLITE = importlib.util.find_spec("aiosqlite") is not None

pytestmark_db = pytest.mark.skipif(
    not _HAS_AIOSQLITE, reason="aiosqlite not installed; integration test needs a DB"
)


@pytest.fixture
async def db_session():
    """A throwaway in-memory SQLite async session with the schema created.

    Uses the real ORM models (Work/WorkWitness/WorkAlias/BuddhistText), so the
    build runs against genuine SQLAlchemy 2.0 mappings — just on SQLite instead
    of PG. No external services.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models  # noqa: F401  (register all mappers / FKs)
    from app.database import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


async def _seed(session):
    """1 zh + 1 sa sharing a title_sa, 1 SC-, 1 84K-toh, 1 plain T (no title_sa)."""
    from app.models.text import BuddhistText

    rows = [
        # cross-pillar pair sharing the same Skt title (diacritic/case variant)
        BuddhistText(
            cbeta_id="T0235", title_zh="金剛般若波羅蜜經", title_sa="Vajracchedikā Prajñāpāramitā",
            lang="lzh",
        ),
        BuddhistText(
            cbeta_id="GRETIL-vajra", title_zh="", title_sa="vajracchedika prajnaparamita",
            lang="sa",
        ),
        # SuttaCentral
        BuddhistText(cbeta_id="SC-an10.1", title_zh="", title_pi="Kimatthiya Sutta", lang="pi"),
        # 84000
        BuddhistText(cbeta_id="84K-toh2", title_zh="", title_bo="bo title", lang="bo"),
        # plain Taisho, no title_sa → singleton
        BuddhistText(cbeta_id="T0251", title_zh="般若波羅蜜多心經", lang="lzh"),
    ]
    session.add_all(rows)
    await session.commit()


@pytestmark_db
async def test_build_integration_clusters_and_anchors(db_session):
    from sqlalchemy import func, select

    from app.models.text import BuddhistText
    from app.models.work import Work, WorkAlias, WorkWitness

    await _seed(db_session)
    stats = await bw.build(db_session, dry_run=False)

    # 5 texts → 4 works (the zh+sa pair merges into one).
    n_works = (await db_session.execute(select(func.count()).select_from(Work))).scalar()
    n_wit = (await db_session.execute(select(func.count()).select_from(WorkWitness))).scalar()
    assert n_works == 4
    assert n_wit == 5  # every text is a witness of exactly one work
    assert stats.works_created == 4
    assert stats.witnesses_created == 5

    # The Skt cluster: find the work via the skt_title alias, assert 2 witnesses.
    norm = bw.normalize_skt_title("Vajracchedikā Prajñāpāramitā")
    alias = (
        await db_session.execute(
            select(WorkAlias).where(WorkAlias.scheme == "skt_title", WorkAlias.value == norm)
        )
    ).scalar_one()
    cluster_witnesses = (
        await db_session.execute(
            select(WorkWitness).where(WorkWitness.work_id == alias.work_id)
        )
    ).scalars().all()
    assert len(cluster_witnesses) == 2
    canons = {w.canon for w in cluster_witnesses}
    assert canons == {"taisho", "gretil"}
    # the sa witness is a root, the lzh one a translation
    roles = {w.lang: w.role for w in cluster_witnesses}
    assert roles == {"sa": "root", "lzh": "translation"}

    # SC anchored, verified, role=root, canon=pali
    sc_text = (
        await db_session.execute(select(BuddhistText).where(BuddhistText.cbeta_id == "SC-an10.1"))
    ).scalar_one()
    sc_wit = (
        await db_session.execute(select(WorkWitness).where(WorkWitness.text_id == sc_text.id))
    ).scalar_one()
    assert sc_wit.confidence == "verified"
    assert sc_wit.role == "root"
    assert sc_wit.canon == "pali"
    sc_work = (await db_session.execute(select(Work).where(Work.id == sc_wit.work_id))).scalar_one()
    assert sc_work.sc_root_uid == "an10.1"

    # 84000 anchored, verified, translation, kangyur
    toh_text = (
        await db_session.execute(select(BuddhistText).where(BuddhistText.cbeta_id == "84K-toh2"))
    ).scalar_one()
    toh_wit = (
        await db_session.execute(select(WorkWitness).where(WorkWitness.text_id == toh_text.id))
    ).scalar_one()
    assert toh_wit.confidence == "verified"
    assert toh_wit.role == "translation"
    assert toh_wit.canon == "kangyur"
    toh_work = (await db_session.execute(select(Work).where(Work.id == toh_wit.work_id))).scalar_one()
    assert toh_work.toh_number == "2"

    # plain T0251 → singleton, confidence auto, its own work
    plain = (
        await db_session.execute(select(BuddhistText).where(BuddhistText.cbeta_id == "T0251"))
    ).scalar_one()
    plain_wit = (
        await db_session.execute(select(WorkWitness).where(WorkWitness.text_id == plain.id))
    ).scalar_one()
    assert plain_wit.confidence == "auto"
    plain_work_wit_count = (
        await db_session.execute(
            select(func.count()).select_from(WorkWitness).where(WorkWitness.work_id == plain_wit.work_id)
        )
    ).scalar()
    assert plain_work_wit_count == 1  # singleton


@pytestmark_db
async def test_build_is_idempotent(db_session):
    from sqlalchemy import func, select

    from app.models.work import Work, WorkAlias, WorkWitness

    await _seed(db_session)

    s1 = await bw.build(db_session, dry_run=False)
    works_1 = (await db_session.execute(select(func.count()).select_from(Work))).scalar()
    wit_1 = (await db_session.execute(select(func.count()).select_from(WorkWitness))).scalar()
    alias_1 = (await db_session.execute(select(func.count()).select_from(WorkAlias))).scalar()

    # Second run must be a no-op.
    s2 = await bw.build(db_session, dry_run=False)
    works_2 = (await db_session.execute(select(func.count()).select_from(Work))).scalar()
    wit_2 = (await db_session.execute(select(func.count()).select_from(WorkWitness))).scalar()
    alias_2 = (await db_session.execute(select(func.count()).select_from(WorkAlias))).scalar()

    assert (works_1, wit_1, alias_1) == (works_2, wit_2, alias_2)
    assert s2.works_created == 0
    assert s2.witnesses_created == 0
    assert s2.aliases_created == 0
    # first run actually did the work
    assert s1.works_created == 4
    assert s1.witnesses_created == 5


@pytestmark_db
async def test_build_dry_run_writes_nothing(db_session):
    from sqlalchemy import func, select

    from app.models.work import Work, WorkWitness

    await _seed(db_session)
    stats = await bw.build(db_session, dry_run=True)

    n_works = (await db_session.execute(select(func.count()).select_from(Work))).scalar()
    n_wit = (await db_session.execute(select(func.count()).select_from(WorkWitness))).scalar()
    assert n_works == 0
    assert n_wit == 0
    # stats still report what WOULD be created
    assert stats.works_created == 4
    assert stats.witnesses_created == 5


@pytestmark_db
async def test_oversized_skt_cluster_left_as_singletons(db_session):
    """A generic Skt title shared by many texts must NOT fuse into one Work."""
    from sqlalchemy import func, select

    from app.models.text import BuddhistText
    from app.models.work import Work, WorkAlias, WorkWitness

    session = db_session
    session.add_all(
        [
            BuddhistText(
                cbeta_id=f"T100{i}", title_zh=f"经{i}", title_sa="Prajñāpāramitā", lang="lzh"
            )
            for i in range(4)
        ]
    )
    await session.commit()

    # max_skt_cluster=2 → the 4-member cluster is over-broad and skipped.
    stats = await bw.build(session, dry_run=False, max_skt_cluster=2)

    n_skt_alias = (
        await session.execute(
            select(func.count())
            .select_from(WorkAlias)
            .where(WorkAlias.scheme == "skt_title")
        )
    ).scalar()
    assert n_skt_alias == 0  # no merge happened
    assert len(stats.skipped_skt_clusters) == 1
    assert stats.skipped_skt_clusters[0][1] == 4  # cluster size recorded

    # All 4 fell through to singleton works (one witness each) via pass 4.
    n_works = (await session.execute(select(func.count()).select_from(Work))).scalar()
    n_wit = (await session.execute(select(func.count()).select_from(WorkWitness))).scalar()
    assert n_works == 4
    assert n_wit == 4
    assert stats.per_pass.get("pass4_singleton") == 4
    assert stats.per_pass.get("pass1_skt", 0) == 0


@pytestmark_db
async def test_pass1_preserves_cross_pillar_anchor(db_session):
    """A SC- text clustered by title_sa keeps its sc_root_uid + sc_uid alias."""
    from sqlalchemy import select

    from app.models.text import BuddhistText
    from app.models.work import Work, WorkAlias, WorkWitness

    session = db_session
    session.add_all(
        [
            BuddhistText(cbeta_id="T0251b", title_zh="心経", title_sa="Hṛdaya", lang="lzh"),
            BuddhistText(
                cbeta_id="SC-pp.heart", title_zh="", title_pi="Heart", title_sa="hrdaya", lang="pi"
            ),
        ]
    )
    await session.commit()

    await bw.build(session, dry_run=False)

    norm = bw.normalize_skt_title("Hṛdaya")
    alias = (
        await session.execute(
            select(WorkAlias).where(
                WorkAlias.scheme == "skt_title", WorkAlias.value == norm
            )
        )
    ).scalar_one()
    wits = (
        await session.execute(
            select(WorkWitness).where(WorkWitness.work_id == alias.work_id)
        )
    ).scalars().all()
    assert len(wits) == 2  # merged into one work

    # the SC canonical anchor is preserved on the Work (issue #2 from review)
    work = (
        await session.execute(select(Work).where(Work.id == alias.work_id))
    ).scalar_one()
    assert work.sc_root_uid == "pp.heart"
    sc_alias = (
        await session.execute(
            select(WorkAlias).where(
                WorkAlias.scheme == "sc_uid", WorkAlias.value == "pp.heart"
            )
        )
    ).scalar_one_or_none()
    assert sc_alias is not None
    assert sc_alias.work_id == alias.work_id
