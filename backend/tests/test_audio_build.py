"""合成编排的哈希分层。

一个文件名要同时满足两个互相冲突的要求：

* **换编码参数必须换 URL** —— `/audio/` 段发的是
  `Cache-Control: immutable, max-age=31536000`，同名文件在 Cloudflare 边缘
  能活一年。不换名就等于改了个寂寞。
* **换编码参数绝不能重新合成** —— MiniMax 是非确定性的（实测同句同参数
  三次：8.01 / 8.82 / 9.30 秒，极差 14.8%）。心經 H 版是使用者逐轮听审
  才通过的，重合成就是把它扔了重赌一次。

所以哈希必须分两层：``synth_hash`` 只由合成参数决定、给 ``.parts`` 目录命名，
保证断点续传能命中已有 WAV；``content_hash`` 再叠上编码参数、给 mp3 命名。
两者混成一个，二选一必然失败其中之一。
"""

from scripts.audio.build_audio import content_hash_of, synth_hash_of

CFG = {
    "voice_id": "Chinese (Mandarin)_Lyrical_Voice",
    "model": "speech-2.8-hd",
    "speed": 1.0,
    "bitrate": "64k",
}
RAW = "般若波羅蜜多心經\n唐三藏法師玄奘譯\n觀自在菩薩行深般若波羅蜜多時"
PRON = ["般若/(bo1)(re3)", "波羅蜜/(bo1)(luo2)(mi4)"]


def test_bitrate_does_not_change_synth_hash() -> None:
    """⭐ 换码率不能动 synth_hash —— 动了 .parts 目录就找不到，会重新调 API。"""
    a = synth_hash_of(CFG, RAW, PRON)
    b = synth_hash_of({**CFG, "bitrate": "128k"}, RAW, PRON)
    assert a == b


def test_bitrate_does_change_content_hash() -> None:
    """⭐ 换码率必须换 content_hash —— 不换名 Cloudflare 会供一年旧文件。"""
    a = content_hash_of(synth_hash_of(CFG, RAW, PRON), CFG)
    b = content_hash_of(synth_hash_of(CFG, RAW, PRON), {**CFG, "bitrate": "128k"})
    assert a != b


def test_synth_hash_is_blind_to_encoding_only_keys() -> None:
    """合成层不该看见任何编码参数，否则以后加一个就断一次续传。"""
    base = synth_hash_of(CFG, RAW, PRON)
    for extra in ({"bitrate": "48k"}, {"sample_rate": 44100}, {"channels": 2}):
        assert synth_hash_of({**CFG, **extra}, RAW, PRON) == base


def test_text_change_moves_both_hashes() -> None:
    """经文改了，音频就过期了 —— 两层都必须变。"""
    s1, s2 = synth_hash_of(CFG, RAW, PRON), synth_hash_of(CFG, RAW + "，照見五蘊皆空", PRON)
    assert s1 != s2
    assert content_hash_of(s1, CFG) != content_hash_of(s2, CFG)


def test_pronunciation_change_moves_both_hashes() -> None:
    """补词典是最常见的重生成场景 —— 早期版本只 hash 正文，hash 纹丝不动。"""
    s1 = synth_hash_of(CFG, RAW, PRON)
    s2 = synth_hash_of(CFG, RAW, [*PRON, "罣礙/(gua4)(ai4)"])
    assert s1 != s2
    assert content_hash_of(s1, CFG) != content_hash_of(s2, CFG)


def test_voice_and_speed_move_both_hashes() -> None:
    for change in ({"voice_id": "other"}, {"speed": 0.9}, {"model": "speech-2.6"}):
        s = synth_hash_of({**CFG, **change}, RAW, PRON)
        assert s != synth_hash_of(CFG, RAW, PRON)


def test_hashes_are_hex_sha256() -> None:
    """入库字段是 String(64)，非 64 位十六进制会被截断或报错。"""
    s = synth_hash_of(CFG, RAW, PRON)
    c = content_hash_of(s, CFG)
    for h in (s, c):
        assert len(h) == 64
        assert all(ch in "0123456789abcdef" for ch in h)
