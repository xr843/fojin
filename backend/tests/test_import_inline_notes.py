"""夹注位置从 XML 正文搬到库里正文（两份正文有格式差、或库里手工改过）。"""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "import_inline_notes", Path(__file__).resolve().parent.parent / "scripts" / "import_inline_notes.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_remap_across_format_difference():
    """库里正文是旧版解析（「┌」处为全角空格、少一个换行）：夹注跟着前面的字走。"""
    parsed = "大般若經┌四百卷\n\n骸骨。拯濟。" * 5
    stored = "大般若經　四百卷\n骸骨。拯濟。" * 5
    i = parsed.index("骸骨。") + 3
    notes = [{"offset": i, "text": "上戶皆反"}]
    (out, dropped) = mod.remap_notes(parsed, stored, notes)
    assert dropped == 0
    assert stored[: out[0]["offset"]].endswith("骸骨。")


def test_note_dropped_when_context_differs():
    """夹注前后的字在库里被改掉了（手工修过的卷）：不猜，丢掉这一条。"""
    parsed = "甲乙丙丁戊己庚辛壬癸" * 6 + "子丑寅卯"
    stored = "甲乙丙丁戊己庚辛壬癸" * 6 + "辰巳午未"
    notes = [{"offset": len(parsed) - 2, "text": "注"}]
    out, dropped = mod.remap_notes(parsed, stored, notes)
    assert (out, dropped) == ([], 1)


def test_juan_skipped_when_bodies_differ_a_lot():
    assert mod.remap_notes("如是我聞一時佛在", "爾時世尊告諸比丘", [{"offset": 2, "text": "x"}]) is None


def test_reordered_juan_located_by_unique_context():
    """段落次序被调过：逐条按前 8 字在库里找，恰好一处才放；出现两次的不猜。"""
    parsed = "第一段文字在此處。" + "第二段甲乙丙丁戊己" + "重複重複重複重複"
    stored = "重複重複重複重複" + "第二段甲乙丙丁戊己" + "第一段文字在此處。" + "重複重複重複重複"
    notes = [{"offset": 9, "text": "注一"}, {"offset": len(parsed), "text": "注二"}]
    out, dropped = mod.locate_by_context(parsed, stored, notes)
    assert dropped == 1
    assert stored[: out[0]["offset"]].endswith("第一段文字在此處。")

