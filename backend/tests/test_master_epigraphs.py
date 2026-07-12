"""祖师长廊 — the epigraph shown on each master's gallery card.

The gallery is an extension of FoJin's citation discipline, not an exception to
it. These tests guard the one invariant that makes that true: a master's card
either carries a line WITH a checkable source, or it carries no line at all.

The quotes themselves were verified character-for-character against production
on 2026-07-12 (whitespace/punctuation normalized — CBETA content hard-wraps
mid-word, so a naive substring check false-negatives). What the suite can still
guard, cheaply and forever, is that nobody later adds a quote without a source.
"""

import pytest

from app.services.master_profiles import MASTERS, list_masters

# Verified 2026-07-12 against fojin.app: each line occurs verbatim in the cited
# text, and the cited text is that master's own work (or, for 鸠摩罗什, his
# translation — the text FoJin already scopes his RAG to).
EXPECTED_VERIFIED = {
    "nagarjuna": ("T1564", 40),
    "zhiyi": ("T1911", 53),
    "huineng": ("T2008", 58),
    "xuanzang": ("T1585", 44),
    "fazang": ("T1866", 8038),
    "kumarajiva": ("T0262", 6513),
    "ouyi": ("T1939", 8109),
}


def test_every_epigraph_carries_a_checkable_source():
    """No line may appear on a card without somewhere to go and check it."""
    for mid, m in MASTERS.items():
        ep = m.epigraph
        if ep is None:
            continue
        assert ep.quote.strip(), f"{mid}: epigraph with an empty quote"
        assert ep.cbeta_id.strip(), f"{mid}: quote without a CBETA id"
        assert ep.title_zh.strip(), f"{mid}: quote without a text title"
        assert ep.text_id > 0, f"{mid}: quote without a reader-resolvable text_id"
        assert ep.juan > 0, f"{mid}: quote without a fascicle number"


def test_only_the_verified_masters_have_an_epigraph():
    """Masters whose own writing we don't host must show nothing.

    Eight of the fifteen are in that position (印光/虚云/米拉日巴/阿姜查/宗喀巴/
    阿底峡/觉音/马哈希) — each confirmed against the corpus, not assumed.

    The reverse error is just as bad and we already made it: the first cut left
    玄奘 and 蕅益 at 未设 while 《成唯識論》(T1585) and 《教觀綱宗》(T1939) sat in the
    corpus, so their cards claimed we hold none of their writing. That claim is
    now gone from the UI, and scripts/verify_master_epigraphs.py checks the
    negative case against the DB so it cannot silently come back.
    """
    with_epigraph = {mid for mid, m in MASTERS.items() if m.epigraph is not None}
    assert with_epigraph == set(EXPECTED_VERIFIED), (
        "The set of masters carrying a quote changed. A new quote must first be "
        "verified verbatim against that master's own work in our corpus."
    )


@pytest.mark.parametrize(("master_id", "expected"), sorted(EXPECTED_VERIFIED.items()))
def test_epigraph_points_at_the_verified_source(master_id, expected):
    cbeta_id, text_id = expected
    ep = MASTERS[master_id].epigraph
    assert ep is not None
    assert ep.cbeta_id == cbeta_id
    assert ep.text_id == text_id


def test_epigraph_text_lies_inside_the_masters_own_rag_scope():
    """The line on a master's card must come from a text that master is scoped to.

    This is the invariant that would have caught the 慧能 bug: his fojin_text_ids
    were guessed ([8169, 6513] — 永嘉集 by 玄覺, and 法華經), so the persona was
    hard-scoped to a text he did not write and could never cite 壇經 — while his
    card quotes 壇經. Card and RAG scope disagreeing is the smell; assert they can't.

    Masters with an EMPTY scope are exempt: `[]` means "no indexed corpus" (see
    _master_text_scope in chat.py) and those masters carry no epigraph anyway.
    """
    for mid, m in MASTERS.items():
        if m.epigraph is None or not m.fojin_text_ids:
            continue
        assert m.epigraph.text_id in m.fojin_text_ids, (
            f"{mid}: card quotes text_id={m.epigraph.text_id} "
            f"({m.epigraph.cbeta_id}) but the persona is scoped to "
            f"{m.fojin_text_ids} — the master cannot actually cite his own epigraph."
        )


# The RAG scope is a HARD filter, and getting it wrong is not cosmetic: a 2026-05-07
# production trace had 楞严经 leaking into Ajahn Chah's context. These IDs were
# resolved against the live corpus on 2026-07-12 — pin them so a future guess can't
# silently replace a verified id.
EXPECTED_SCOPE = {
    "nagarjuna": [39, 40, 41, 7806, 7708],  # 大智度論/中論/十二門論/迴諍論/十住毘婆沙論
    "zhiyi": [53, 52, 8085, 6513],  # 摩訶止觀/法華文句/小止觀/法華經
    "huineng": [58, 63],  # 六祖壇經 T2008 / 金剛經 T0235b
    "fazang": [8038],  # 華嚴一乘教義分齊章 T1866
    "kumarajiva": [6513],  # 妙法蓮華經 T0262（其译）
    "xuyun": [],  # 《法彙》不在 CBETA — no indexed corpus
}


@pytest.mark.parametrize(("master_id", "expected"), sorted(EXPECTED_SCOPE.items()))
def test_master_rag_scope_pinned_to_verified_text_ids(master_id, expected):
    assert MASTERS[master_id].fojin_text_ids == expected, (
        f"{master_id}: RAG scope changed. text_ids are a hard filter — verify any new "
        f"id actually is that master's own work before changing this."
    )


def test_list_masters_exposes_epigraph_to_the_frontend():
    masters = list_masters()
    assert len(masters) == len(MASTERS)

    by_id = {m["id"]: m for m in masters}
    for mid in MASTERS:
        assert "epigraph" in by_id[mid], f"{mid}: gallery card has no epigraph field"

    huineng = by_id["huineng"]["epigraph"]
    assert huineng is not None
    assert huineng["quote"] == "菩提本無樹，明鏡亦非臺"
    assert huineng["cbeta_id"] == "T2008"
    assert huineng["text_id"] == 58  # deep-links straight into the reader
    assert huineng["juan"] == 1

    # A master we hold no writing for says so by omission, not by invention.
    assert by_id["yinguang"]["epigraph"] is None
