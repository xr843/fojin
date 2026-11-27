"""检索段落附夹注（只给模型看）：位置、换行、上限、找不到。"""

from app.services.inline_note_context import splice_notes

CONTENT = "前文。\n摩訶般若波羅蜜經四十卷\n小品般若十卷。後文。"


def test_notes_spliced_after_their_character_and_newlines_kept():
    chunk = "摩訶般若波羅蜜經四十\n卷小品般若十卷。"  # 检索段落的硬换行位置与正文不同
    off1 = CONTENT.index("四十卷") + 3  # 跟在「卷」后
    off2 = CONTENT.index("十卷。") + 2  # 跟在「小品般若十卷」的「卷」后
    out = splice_notes(chunk, CONTENT, [(off1, "弘始五年出"), (off2, "第七譯")])
    assert out == "摩訶般若波羅蜜經四十\n卷（弘始五年出）小品般若十卷（第七譯）。"


def test_notes_outside_the_chunk_are_ignored():
    chunk = "小品般若十卷。"
    assert splice_notes(chunk, CONTENT, [(CONTENT.index("四十卷") + 3, "不在本段")]) is None


def test_long_notes_capped_at_chunk_length():
    chunk = "小品般若十卷。"
    off = CONTENT.index("十卷。") + 2
    out = splice_notes(chunk, CONTENT, [(off, "長" * 50)])
    assert out == "小品般若十卷（" + "長" * 7 + "……）。"


def test_chunk_not_found_or_ambiguous_returns_none():
    assert splice_notes("不在正文裏", CONTENT, [(3, "x")]) is None
    assert splice_notes("般若", CONTENT, [(3, "x")]) is None  # 出现两处，不猜


def test_context_block_shows_notes_but_source_text_unchanged():
    """交给模型的上下文用附了夹注的 llm_text；chunk_text（引文核对、前端显示）不变。"""
    from app.services.rag_retrieval import _format_context_block

    r = {"text_id": 1, "juan_num": 4, "chunk_index": 0, "title_zh": "開元釋教錄", "score": 1.0,
         "chunk_text": "四十卷小品", "llm_text": "四十卷（弘始五年出）小品"}  # fmt: skip
    block = _format_context_block(r)
    assert "四十卷（弘始五年出）小品" in block
    assert r["chunk_text"] == "四十卷小品"
    assert "四十卷小品" in _format_context_block({**r, "llm_text": None})
