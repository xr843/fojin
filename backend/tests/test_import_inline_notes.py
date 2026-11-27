"""夹注位置从 XML 正文搬到库里正文（两份正文有格式差、或库里手工改过）。"""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "import_inline_notes", Path(__file__).resolve().parent.parent / "scripts" / "import_inline_notes.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_format_difference_located_by_context():
    """库里正文是旧版解析（「┌」处为全角空格、换行不同）：按夹注前 8 字（不计换行）找回位置。"""
    parsed = "大般若經┌四百卷\n\n骸骨。一二三四五拯濟。"
    stored = "大般若經\u3000四百卷\n骸骨。一二三\n四五拯濟。"
    i = parsed.index("五") + 1
    out, dropped = mod.locate_by_context(parsed, stored, [{"offset": i, "text": "注"}])
    assert dropped == 0
    assert stored[: out[0]["offset"]].replace("\n", "").endswith("一二三四五")


def test_reordered_juan_located_by_unique_context():
    """段落次序被调过：逐条按前 8 字在库里找，恰好一处才放；出现两次的不猜。"""
    parsed = "第一段文字在此處。" + "第二段甲乙丙丁戊己" + "重複重複重複重複"
    stored = "重複重複重複重複" + "第二段甲乙丙丁戊己" + "第一段文字在此處。" + "重複重複重複重複"
    notes = [{"offset": 9, "text": "注一"}, {"offset": len(parsed), "text": "注二"}]
    out, dropped = mod.locate_by_context(parsed, stored, notes)
    assert dropped == 1
    assert stored[: out[0]["offset"]].endswith("第一段文字在此處。")

