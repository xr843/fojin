"""生成音色试听样本 —— 「在线读诵」功能的 KILL GATE。

产出 samples/ 下若干 mp3，由人试听决定这个功能做不做。
同时验证 <phoneme alphabet="sapi"> 是否真的生效（听「佛」是 fó 还是 fú）。

用法：
    cd backend
    export AZURE_SPEECH_KEY=... AZURE_SPEECH_REGION=eastasia
    python -m scripts.audio.sample_voices --out /tmp/fojin-voice-samples
"""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.audio.g2p import to_ssml
from scripts.audio.tts_azure import synthesize

# 金剛般若波羅蜜經（T0235，姚秦 鳩摩羅什譯）開經段。
#
# 为什么用羅什本而不是 fojin 上阅读量更高的菩提流支本（T0236a）：
# 念诵传统、流通本、早晚课用的都是羅什本；菩提流支本是研究对读用的，
# 没有人会照它念。阅读量高 ≠ 听经需求高。
#
# 这一段刻意选含「佛」「舍衛」「比丘」「須菩提」「祇樹給孤獨園」的文字 ——
# 这几处正是词典在纠正的，听一遍就能判断 phoneme 有没有生效。
SAMPLE_TEXT = (
    "如是我聞：一時，佛在舍衛國祇樹給孤獨園，與大比丘眾千二百五十人俱。"
    "爾時，世尊食時，著衣持鉢，入舍衛大城乞食。"
    "於其城中，次第乞已，還至本處。飯食訖，收衣鉢，洗足已，敷座而坐。"
    "時，長老須菩提在大眾中即從座起，偏袒右肩，右膝著地，合掌恭敬而白佛言："
    "「希有！世尊！如來善護念諸菩薩，善付囑諸菩薩。」"
)

# 候选音色。男声优先 —— 读诵场景女声播音腔出戏更明显。
VOICES = [
    "zh-CN-YunzeNeural",  # 成熟男声，偏沉稳
    "zh-CN-YunjianNeural",  # 男声，偏叙事
    "zh-CN-YunxiNeural",  # 男声，偏年轻
    "zh-CN-XiaoxuanNeural",  # 女声，对照用
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="音色试听样本生成")
    parser.add_argument("--out", default="samples", help="输出目录")
    parser.add_argument("--voices", nargs="*", default=VOICES)
    parser.add_argument(
        "--no-lexicon",
        action="store_true",
        help="不用词典直接念原文 —— 用于 A/B 对照，听出词典有没有生效",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    for voice in args.voices:
        for use_lex in [False] if args.no_lexicon else [True, False]:
            tag = "lex" if use_lex else "raw"
            ssml = to_ssml(SAMPLE_TEXT, voice) if use_lex else to_ssml(SAMPLE_TEXT, voice, lexicon={})
            path = out_dir / f"{voice}-{tag}.mp3"
            boundaries = synthesize(ssml, path)
            print(f"✓ {path}  词边界 {len(boundaries)} 个")

    print()
    print("=" * 66)
    print("请试听。判据：放给一位法师听，他会不会皱眉。")
    print()
    print("同时确认 <phoneme> 是否生效 —— 对比 *-lex.mp3 与 *-raw.mp3：")
    print("  「佛在舍衛國」   lex 应读 fó zài shè wèi guó，raw 会读 fú zài shě wèi guó")
    print("  「祇樹給孤獨園」 lex 应读 qí shù jǐ gū dú yuán，raw 会读 …gěi gū dú…")
    print("  「大比丘眾」     lex 应读 dà bǐ qiū zhòng")
    print()
    print("若 lex 与 raw 听感一致 → phoneme 未生效 → 改走 Custom Lexicon 或换厂商")
    print("若音色整体出戏     → 功能终止，不要继续 Task 4")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
