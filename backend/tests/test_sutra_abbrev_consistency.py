"""同一个简称，三个模块必须指向同一部经。

一部佛经常有数本汉译。《楞伽經》就有三本：T0670 楞伽阿跋多羅寶經（求那跋陀羅，
4 卷）、T0671 入楞伽經（菩提流支，10 卷）、T0672 大乘入楞伽經（實叉難陀，7 卷）。
所以「楞伽经」这三个字必须由代码选定一本——而它此前选了两本：

- `search._SUTRA_ABBREV`            → 入楞伽經    （T0671）
- `precise_retrieval._TITLE_ALIASES` → 楞伽阿跋多羅寶經（T0670）
- `rag_retrieval._ROOT_SUTRA_ALIASES` → T0670

结果是：读者在 /search 打「楞伽经」，排第一的是入楞伽經；同一个人拿同一个词去问
AI，引的是楞伽阿跋多羅寶經。同一个词，两部经，取决于他从哪个门进来。

这类分歧靠读代码发现不了——三张表分处三个文件、格式还不一样（两张给标题，一张
给 cbeta_id）。所以钉成测试：**共有的键必须同解**。新增简称时若只改一处，这里会红。
"""

import pytest

from app.services.precise_retrieval import _TITLE_ALIASES
from app.services.rag_retrieval import _ROOT_SUTRA_ALIASES
from app.services.search import _SUTRA_ABBREV

SHARED_KEYS = sorted(set(_SUTRA_ABBREV) & set(_TITLE_ALIASES))


def test_the_two_tables_actually_overlap():
    """守住上面那个交集：两张表若哪天不再共享任何键，下面的用例会全部空转。"""
    assert len(SHARED_KEYS) >= 10
    assert "楞伽经" in SHARED_KEYS


@pytest.mark.parametrize("abbrev", SHARED_KEYS)
def test_search_and_precise_retrieval_agree(abbrev):
    assert _SUTRA_ABBREV[abbrev] == _TITLE_ALIASES[abbrev], (
        f"「{abbrev}」在搜索里是《{_SUTRA_ABBREV[abbrev]}》，"
        f"在精确检索里是《{_TITLE_ALIASES[abbrev]}》——同一个词指向了两部经"
    )


# rag_retrieval 用 cbeta_id 而不是标题，无法直接比对，所以在这里把两边钉在一起。
# 只列那些三张表都收了的简称；改动任何一边都必须同步改这里。
_RAG_ALIAS_TITLES = {
    "T0251": "般若波羅蜜多心經",
    "T0262": "妙法蓮華經",
    "T0475": "維摩詰所說經",
    "T0412": "地藏菩薩本願經",
    "T0670": "楞伽阿跋多羅寶經",
    "T0842": "大方廣圓覺修多羅了義經",
}


@pytest.mark.parametrize("alias,cbeta_id", sorted(_ROOT_SUTRA_ALIASES.items()))
def test_rag_alias_agrees_with_the_title_tables(alias, cbeta_id):
    """RAG 的本经保底若和标题表选了不同的译本，答案与搜索会各说各话。"""
    expected_title = _RAG_ALIAS_TITLES.get(cbeta_id)
    if expected_title is None:
        pytest.skip(f"{cbeta_id} 不在三表共有范围内")
    for table_name, table in (("search", _SUTRA_ABBREV), ("precise", _TITLE_ALIASES)):
        title = table.get(alias)
        if title is None:
            continue
        assert title == expected_title, (
            f"「{alias}」：RAG 保底指向 {cbeta_id}《{expected_title}》，"
            f"而 {table_name} 指向《{title}》"
        )
