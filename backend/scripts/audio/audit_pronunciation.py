"""扫描一卷经文，列出词典未覆盖的汉字，按频次排序。

用途：合成前评估残余读音风险。词典覆盖不了的字会走 pypinyin 默认读音，
其中高频的那些就是下一批该人工审定的候选。

Task 1 的 golden 测试只证明「已知的错已修」，证明不了「还有多少未知的错」。
合成前必须知道残余风险面 —— 否则就是 ¥150 换 70 小时无法验收的音频。

用法：
    cd backend
    python -m scripts.audio.audit_pronunciation --text-id 10036 --juan 1
    python -m scripts.audio.audit_pronunciation --file /path/to/juan.txt --top 40
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import urllib.request
from pathlib import Path

from pypinyin import Style, lazy_pinyin
from scripts.audio.g2p import _is_han, load_lexicon, segment

DEFAULT_API = "https://fojin.app/api"

# ⚠️ 必须带 User-Agent：Cloudflare 对 urllib 的默认 UA（Python-urllib/3.x）
#    直接回 403，且报错信息里看不出是被 CF 挡的。已实测：裸 urllib → 403，
#    带任意自定义 UA → 200。
_UA = {"User-Agent": "fojin-audio-pipeline/1.0"}


def fetch_juan(api_base: str, text_id: int, juan: int) -> str:
    req = urllib.request.Request(
        f"{api_base}/texts/{text_id}/juans/{juan}", headers=_UA
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp).get("content") or ""


def audit(text: str, top: int) -> int:
    lexicon = load_lexicon()
    uncovered: collections.Counter[str] = collections.Counter()
    covered_chars = 0
    total_han = sum(1 for ch in text if _is_han(ch))

    for frag, pinyin in segment(text, lexicon):
        if pinyin is not None:
            covered_chars += sum(1 for ch in frag if _is_han(ch))
            continue
        uncovered.update(ch for ch in frag if _is_han(ch))

    print(f"汉字总数           : {total_han}")
    print(f"词典覆盖           : {covered_chars} ({covered_chars / max(total_han, 1) * 100:.1f}%)")
    print(f"未覆盖不同字数     : {len(uncovered)}")
    print()
    print(f"未覆盖字 TOP {top}（这些走 pypinyin 默认读音，是残余风险面）：")
    print(f"{'字':<4}{'频次':>6}  pypinyin 默认")
    for ch, n in uncovered.most_common(top):
        default = lazy_pinyin(ch, style=Style.TONE3, neutral_tone_with_five=True)
        print(f"{ch:<4}{n:>6}  {default[0] if default else '?'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="读音覆盖度审计")
    parser.add_argument("--text-id", type=int, help="经号（走线上 API 取正文）")
    parser.add_argument("--juan", type=int, default=1)
    parser.add_argument("--file", help="改为读本地纯文本文件")
    parser.add_argument("--api-base", default=DEFAULT_API)
    parser.add_argument("--top", type=int, default=30)
    args = parser.parse_args(argv)

    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    elif args.text_id:
        text = fetch_juan(args.api_base, args.text_id, args.juan)
    else:
        parser.error("需要 --text-id 或 --file 之一")
    if not text:
        print("未取到正文", file=sys.stderr)
        return 1
    return audit(text, args.top)


if __name__ == "__main__":
    raise SystemExit(main())
