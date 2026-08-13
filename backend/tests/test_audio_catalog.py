"""读诵目录的聚合形状。

音频按**卷**存（``text_audio`` 的键含 juan_num），但索引页要按**经**列：
使用者找的是「哪部经能听」，不是「哪一卷能听」。中间这层聚合没有 DB
参与也能测 —— 把 ORM 行拼成列表项的规则本身就是逻辑。

⚠️ 排序刻意用「总时长升序」而非 text_id：短经先上是这个功能的现实
（心經 1.7 分钟 vs 壇經 134 分钟），让人一眼看到能听完的那几部。
"""

from unittest.mock import MagicMock

from app.services.audio import group_audio_by_text


def _row(text_id: int, juan: int, ms: int, title: str, translator: str | None = "玄奘",
         dynasty: str | None = "唐", taisho: str | None = "T0251") -> tuple:
    audio = MagicMock()
    audio.text_id, audio.juan_num, audio.duration_ms = text_id, juan, ms
    audio.engine, audio.voice_id = "minimax", "Lyrical"
    audio.audio_path = f"{text_id}/{juan}-abcd1234.mp3"
    text = MagicMock()
    text.id, text.title_zh, text.translator = text_id, title, translator
    text.dynasty, text.taisho_id = dynasty, taisho
    return (audio, text)


def test_one_juan_one_item() -> None:
    items = group_audio_by_text([_row(9, 1, 101_363, "般若波羅蜜多心經")])
    assert len(items) == 1
    it = items[0]
    assert it["text_id"] == 9
    assert it["title_zh"] == "般若波羅蜜多心經"
    assert it["translator"] == "玄奘"
    assert it["dynasty"] == "唐"
    assert it["taisho_id"] == "T0251"
    assert it["juan_count"] == 1
    assert it["total_duration_ms"] == 101_363
    assert it["juans"] == [{"juan_num": 1, "duration_ms": 101_363, "url": "/audio/9/1-abcd1234.mp3"}]


def test_multiple_juans_collapse_into_one_item() -> None:
    """一经多卷只出一行，时长求和 —— 否则地藏經会占满整页。"""
    items = group_audio_by_text([
        _row(24, 1, 300_000, "地藏菩薩本願經"),
        _row(24, 2, 200_000, "地藏菩薩本願經"),
    ])
    assert len(items) == 1
    assert items[0]["juan_count"] == 2
    assert items[0]["total_duration_ms"] == 500_000
    assert [j["juan_num"] for j in items[0]["juans"]] == [1, 2]


def test_juans_are_sorted_even_if_rows_are_not() -> None:
    """卷次必须升序 —— 列表里「第2卷」排在「第1卷」前面是明显的错。"""
    items = group_audio_by_text([
        _row(24, 3, 100, "地藏菩薩本願經"),
        _row(24, 1, 100, "地藏菩薩本願經"),
        _row(24, 2, 100, "地藏菩薩本願經"),
    ])
    assert [j["juan_num"] for j in items[0]["juans"]] == [1, 2, 3]


def test_items_sorted_by_total_duration_ascending() -> None:
    """短的排前面 —— 能一次听完的那几部才是这个功能的现实入口。"""
    items = group_audio_by_text([
        _row(24, 1, 500_000, "地藏菩薩本願經"),
        _row(9, 1, 101_363, "般若波羅蜜多心經"),
        _row(7, 1, 300_000, "金剛般若波羅蜜經"),
    ])
    assert [it["text_id"] for it in items] == [9, 7, 24]


def test_missing_translator_and_dynasty_do_not_crash() -> None:
    """CBETA 里有相当一批经没有译者著录，不能因此让整页 500。"""
    items = group_audio_by_text([_row(6562, 1, 1000, "普門品經", translator=None,
                                      dynasty=None, taisho=None)])
    assert items[0]["translator"] is None
    assert items[0]["dynasty"] is None
    assert items[0]["taisho_id"] is None


def test_empty_input_gives_empty_list() -> None:
    assert group_audio_by_text([]) == []
