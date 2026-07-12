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
    "fazang": ("T1866", 8038),
    "kumarajiva": ("T0262", 6513),
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

    Ten of the fifteen are in that position (玄奘/印光/蕅益/虚云/米拉日巴/阿姜查/
    宗喀巴/阿底峡/觉音/马哈希). Showing them a plausible-sounding line we cannot
    open would be exactly the failure this product exists to prevent — so if a
    future edit adds one, this test should make someone justify it.
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
