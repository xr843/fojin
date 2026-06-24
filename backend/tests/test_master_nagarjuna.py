"""Profile presence + grounding contract for the 龙树 (Nāgārjuna) master.

龙树 is added as the first 印度 (Indian) master — the Madhyamaka headwater
that the existing 鸠摩罗什 (his translator) and 宗喀巴 (应成中观 inheritor)
personas already point back to. Unlike the corpus-less masters that fall
back to full-library RAG (``fojin_text_ids=[]``), 龙树's core treatises ARE
in FoJin's CBETA full-text, so his persona MUST be tradition-scoped to them
— the scope is the whole reason he was chosen, and an empty-list fallback
would silently defeat it (see ``chat._master_scope_text_ids`` three-state
contract).

Corpus IDs verified live against /api/search (all has_content=True):
大智度論 T1509 id=39 · 中論 T1564 id=40 · 十二門論 T1568 id=41 ·
迴諍論 T1631 id=7806 · 十住毘婆沙論 T1521 id=7708.
"""

from app.services.master_profiles import get_master, list_masters


def test_nagarjuna_is_registered():
    m = get_master("nagarjuna")
    assert m is not None
    assert "龙树" in m.name_zh
    assert m.name_en == "Nagarjuna"


def test_nagarjuna_tradition_is_madhyamaka():
    m = get_master("nagarjuna")
    assert "中观" in m.tradition


def test_nagarjuna_is_corpus_scoped_not_empty_fallback():
    """The persona must scope to 龙树's own treatises (vector + precise),
    not fall back to full-corpus RAG like the corpus-less masters."""
    m = get_master("nagarjuna")
    assert m.fojin_text_ids, "龙树 must be tradition-scoped, not an empty []-fallback"
    assert 40 in m.fojin_text_ids  # 中論 — his root treatise
    assert 39 in m.fojin_text_ids  # 大智度論 — the encyclopedic 般若 commentary


def test_nagarjuna_prompt_carries_core_doctrine_and_scaffold():
    m = get_master("nagarjuna")
    sp = m.system_prompt
    assert sp.startswith("你是龙树")
    assert "八不中道" in sp
    assert "缘起性空" in sp or "性空" in sp
    assert "[追问]" in sp  # progressive follow-up scaffold preserved


def test_nagarjuna_listed_for_frontend_selector():
    entries = list_masters()
    ids = [e["id"] for e in entries]
    assert "nagarjuna" in ids
    entry = next(e for e in entries if e["id"] == "nagarjuna")
    assert set(entry) >= {"id", "name_zh", "name_en", "tradition", "dates", "description"}
