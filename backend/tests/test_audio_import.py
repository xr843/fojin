"""入库前的重复键检测。

``text_audio`` 的唯一键是 ``(text_id, juan_num, lang, voice_id)``，而
``import_one`` 遇到已存在的行是**先删后插**。所以同一次运行里若出现两份
指向同一把键的 cues.json，后处理的那份会静默顶掉前一份 —— 而顺序由
``sorted()`` 的**字典序**决定，跟新旧无关。

实测踩过：心經从 128k 重编码到 64k 后，产物目录里同时躺着
``1-7891dd17.cues.json``（新，64k）和 ``1-ba9307ad.cues.json``（旧，128k）。
字典序 ``7`` < ``b``，于是**旧的最后处理、赢了**，线上会回退到 128k
而全程没有任何报错。

宁可让它当场报错，也不要让人对着一份"部署成功"的日志找为什么没生效。
"""

import pytest
from scripts.audio.import_audio import audio_key, find_duplicate_keys


def _meta(text_id: int, juan: int, path: str, voice: str = "V", lang: str = "zh") -> dict:
    return {
        "text_id": text_id, "juan_num": juan, "lang": lang,
        "voice_id": voice, "audio_path": path,
    }


def test_no_duplicates_returns_empty() -> None:
    metas = [_meta(9, 1, "9/1-a.mp3"), _meta(9, 2, "9/2-b.mp3"), _meta(7, 1, "7/1-c.mp3")]
    assert find_duplicate_keys(metas) == {}


def test_same_juan_twice_is_flagged() -> None:
    """⭐ 就是重编码那次的形态：同经同卷同音色，两个不同的 hash 文件名。"""
    metas = [_meta(9, 1, "9/1-7891dd17.mp3"), _meta(9, 1, "9/1-ba9307ad.mp3")]
    dupes = find_duplicate_keys(metas)
    assert list(dupes) == [(9, 1, "zh", "V")]
    assert sorted(dupes[(9, 1, "zh", "V")]) == ["9/1-7891dd17.mp3", "9/1-ba9307ad.mp3"]


def test_different_voice_is_not_a_duplicate() -> None:
    """同一卷并存多个音色是**设计允许**的（表的唯一键含 voice_id）。"""
    metas = [_meta(9, 1, "9/1-a.mp3", voice="Lyrical"), _meta(9, 1, "9/1-b.mp3", voice="Calm")]
    assert find_duplicate_keys(metas) == {}


def test_different_lang_is_not_a_duplicate() -> None:
    metas = [_meta(9, 1, "9/1-a.mp3", lang="zh"), _meta(9, 1, "9/1-b.mp3", lang="en")]
    assert find_duplicate_keys(metas) == {}


def test_three_way_collision_lists_all() -> None:
    metas = [_meta(9, 1, f"9/1-{h}.mp3") for h in ("aa", "bb", "cc")]
    assert len(find_duplicate_keys(metas)[(9, 1, "zh", "V")]) == 3


@pytest.mark.parametrize("missing", ["text_id", "juan_num", "lang", "voice_id"])
def test_key_fields_are_all_required(missing: str) -> None:
    """四个字段一个都不能缺 —— 缺了就当场 KeyError，不要用默认值蒙混。

    早先这里给 lang/voice_id 配了默认值，结果检测与 ``import_one`` 各推导
    一次键：检测放行、入库照撞。共用 ``audio_key`` 是为了根除这种漂移，
    所以本用例钉的是「两边同样地严」。
    """
    m = _meta(9, 1, "9/1-a.mp3")
    del m[missing]
    with pytest.raises(KeyError):
        find_duplicate_keys([m])


def test_duplicate_check_uses_the_same_key_as_import() -> None:
    """检测用的键必须与入库用的键逐字段相同。"""
    m = _meta(9, 1, "9/1-a.mp3")
    assert audio_key(m) == (9, 1, "zh", "V")
