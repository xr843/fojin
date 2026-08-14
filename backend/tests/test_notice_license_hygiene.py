"""NOTICE 的许可声明卫生 —— 三条在 2026-08-13 审计里真实踩到的坑。

Apache-2.0 §4(d) 规定 NOTICE 随每一次再分发传播，所以这里写错的许可会被复制到
每一个 fork 和自部署实例。那次审计发现的问题（全部已修）：

  · SuttaCentral 的译文被记成 CC BY-SA，实际是 CC0 —— 而 CC0 献让书正是对方
    创始人本人写的，把它写错会直接削掉「我们认真核过许可」这个立场；
  · 「Academic open access」被当成许可用了 5 次 —— 它不是许可，不说明署名、
    商用、衍生任何一项，给的是虚假的安心；
  · DSBC 被写成开放并「downloaded and indexed locally」，实际它明令
    "reproduction … without permission is prohibited"。

这三条都不是拼写问题，是**会传播出去的合规陈述**，所以用测试钉住。
"""

from pathlib import Path

import pytest

NOTICE = (Path(__file__).resolve().parents[2] / "NOTICE").read_text(encoding="utf-8")


# 不是许可名的模糊说法。它们既不对应任何 SPDX 标识，也不回答「能不能商用 /
# 要不要署名 / 能不能改」——写进 NOTICE 等于什么都没说，却让人以为说了。
BANNED_PSEUDO_LICENSES = [
    "academic open access",
    "open access license",
    "free for academic use",
]


@pytest.mark.parametrize("phrase", BANNED_PSEUDO_LICENSES)
def test_no_pseudo_license_phrases(phrase: str):
    """只查 `License:` 行 —— 历史说明里复述旧错误（"曾被写成 academic open
    access"）是有价值的，不该被门禁误伤；伪许可**作为现行主张**才是问题。"""
    offenders = [
        line.strip()
        for line in NOTICE.splitlines()
        if line.lstrip().lower().startswith("license:") and phrase in line.lower()
    ]
    assert not offenders, (
        f"NOTICE 的许可行里出现了伪许可表述「{phrase}」：{offenders}。"
        f"它不是许可名 —— 请写具体的许可（并附权威来源链接），"
        f"或如实写成「NOT STATED / UNVERIFIED」。"
    )


def _entry(header: str, length: int = 1800) -> str:
    """取某个数据源条目的正文。条目标题右侧有对齐用的空格与统计数字，
    所以按 URL 行定位比按「名称+换行」稳。"""
    start = NOTICE.index(header)
    return NOTICE[start : start + length]


def test_suttacentral_recorded_as_cc0_not_share_alike():
    """SuttaCentral 全部内容（含译文）是 CC0，不是 CC BY-SA。"""
    entry = _entry("https://suttacentral.net\nLicense:")
    assert "CC0" in entry, "SuttaCentral 条目未记为 CC0"
    assert "bilara-data" in entry, (
        "SuttaCentral 条目缺少权威来源链接 —— 许可声明必须可被下一个人复核"
    )
    # CC BY-SA 只应作为「此前记错了」的历史说明出现，不能是当前主张
    for line in entry.splitlines():
        if "CC BY-SA" in line:
            assert "wrongly" in line or "previous" in line.lower(), (
                f"SuttaCentral 条目仍把 CC BY-SA 当作现行许可: {line.strip()!r}"
            )


def test_restrictive_sources_state_their_real_conditions():
    """几个带真实义务的源，义务本身必须写出来，不能只写许可名。"""
    checks = {
        # CBETA 的 B 类文献不在 CC 覆盖范围内，是最容易踩的一条
        "印順": "CBETA 的 Category B 例外未写明",
        # 84000 的署名必须点名 84000 本身，且 ND 禁止改动
        "NO DERIVATIVES": "84000 的 NoDerivatives 条件未写明",
        # DSBC 明令禁止未经许可的复制
        "reproduction of DSBC": "DSBC 的禁止复制条款未写明",
    }
    for needle, msg in checks.items():
        assert needle.lower() in NOTICE.lower(), msg


def test_every_license_claim_is_traceable():
    """凡是断言了具体许可的条目，都要能被复核 —— 附来源链接或标为未核实。"""
    # 粗判：出现具体许可名的段落数，应当不多于「可复核标记」的数量
    claims = NOTICE.lower().count("license: cc")
    traceable = NOTICE.lower().count("verified:") + NOTICE.lower().count("unverified")
    assert traceable >= claims, (
        f"有 {claims} 条具体许可声明，但只有 {traceable} 处可复核标记 —— "
        "每条许可声明都应附 'verified: <url>' 或明确标为 UNVERIFIED"
    )
