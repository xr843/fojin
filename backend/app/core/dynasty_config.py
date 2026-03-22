# backend/app/core/dynasty_config.py
"""Dynasty-to-year mapping shared across stats endpoints.

Keep in sync with frontend/src/data/dynasty_years.ts.
"""

DYNASTIES: list[dict] = [
    {"key": "pre_qin", "name_zh": "先秦", "name_en": "Pre-Qin", "start": -770, "end": -221},
    {"key": "qin", "name_zh": "秦", "name_en": "Qin Dynasty", "start": -221, "end": -206},
    {"key": "western_han", "name_zh": "西汉", "name_en": "Western Han", "start": -206, "end": 8},
    {"key": "eastern_han", "name_zh": "東漢", "name_en": "Eastern Han", "start": 25, "end": 220},
    {"key": "three_kingdoms", "name_zh": "三國", "name_en": "Three Kingdoms", "start": 220, "end": 280},
    {"key": "western_jin", "name_zh": "西晉", "name_en": "Western Jin", "start": 265, "end": 316},
    {"key": "eastern_jin", "name_zh": "東晉", "name_en": "Eastern Jin", "start": 317, "end": 420},
    {"key": "sixteen_kingdoms", "name_zh": "十六國", "name_en": "Sixteen Kingdoms", "start": 304, "end": 439},
    {"key": "southern_dynasties", "name_zh": "南朝", "name_en": "Southern Dynasties", "start": 420, "end": 589},
    {"key": "northern_dynasties", "name_zh": "北朝", "name_en": "Northern Dynasties", "start": 386, "end": 581},
    {"key": "sui", "name_zh": "隋", "name_en": "Sui Dynasty", "start": 581, "end": 618},
    {"key": "tang", "name_zh": "唐", "name_en": "Tang Dynasty", "start": 618, "end": 907},
    {"key": "five_dynasties", "name_zh": "五代", "name_en": "Five Dynasties", "start": 907, "end": 960},
    {"key": "northern_song", "name_zh": "北宋", "name_en": "Northern Song", "start": 960, "end": 1127},
    {"key": "southern_song", "name_zh": "南宋", "name_en": "Southern Song", "start": 1127, "end": 1279},
    {"key": "liao", "name_zh": "遼", "name_en": "Liao Dynasty", "start": 916, "end": 1125},
    {"key": "jin_jurchen", "name_zh": "金", "name_en": "Jin (Jurchen)", "start": 1115, "end": 1234},
    {"key": "yuan", "name_zh": "元", "name_en": "Yuan Dynasty", "start": 1271, "end": 1368},
    {"key": "ming", "name_zh": "明", "name_en": "Ming Dynasty", "start": 1368, "end": 1644},
    {"key": "qing", "name_zh": "清", "name_en": "Qing Dynasty", "start": 1644, "end": 1912},
    {"key": "modern", "name_zh": "近現代", "name_en": "Modern", "start": 1912, "end": 2000},
    {"key": "india", "name_zh": "印度", "name_en": "India", "start": -500, "end": 1200},
    {"key": "japan", "name_zh": "日本", "name_en": "Japan", "start": 600, "end": 1900},
    {"key": "korea", "name_zh": "高麗/朝鮮", "name_en": "Korea", "start": 918, "end": 1910},
    {"key": "tibet", "name_zh": "西藏", "name_en": "Tibet", "start": 600, "end": 1900},
]

# Lookup: name_zh -> dynasty dict
_BY_NAME: dict[str, dict] = {}
for d in DYNASTIES:
    _BY_NAME[d["name_zh"]] = d


# Common aliases from TRANSLATOR_DYNASTIES in scripts_shared.py
_ALIASES: dict[str, str] = {
    "後漢": "東漢",
    "劉宋": "南朝",
    "蕭齊": "南朝",
    "蕭梁": "南朝",
    "曹魏": "三國",
    "吳": "三國",
    "東吳": "三國",
    "北涼": "十六國",
    "後秦": "十六國",
    "姚秦": "十六國",
    "前秦": "十六國",
    "西秦": "十六國",
    "北魏": "北朝",
    "東魏": "北朝",
    "西魏": "北朝",
    "北齊": "北朝",
    "北周": "北朝",
    "宋": "北宋",
    "南齊": "南朝",
    "梁": "南朝",
    "陳": "南朝",
}


def resolve_dynasty(name_zh: str | None) -> dict | None:
    """Resolve a dynasty name (including aliases) to its config entry."""
    if not name_zh:
        return None
    canonical = _ALIASES.get(name_zh, name_zh)
    return _BY_NAME.get(canonical)


def get_year_range(name_zh: str | None) -> tuple[int, int] | None:
    """Return (start, end) year tuple for a dynasty name, or None."""
    d = resolve_dynasty(name_zh)
    if d:
        return (d["start"], d["end"])
    return None
