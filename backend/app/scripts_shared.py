"""Shared constants and utilities for import scripts."""

# CBETA catalog categories mapping
CATEGORIES = {
    "T": ("大正藏", "Taishō"),
    "X": ("卍新纂續藏經", "Xuzangjing"),
    "A": ("趙城金藏", "Zhaocheng Jinzang"),
    "K": ("高麗大藏經", "Goryeo Daejanggyeong"),
    "S": ("宋藏遺珍", "Song Treasures"),
    "F": ("房山石經", "Fangshan Stone Sutras"),
    "C": ("中華大藏經", "Zhonghua Dazangjing"),
    "D": ("國圖善本", "National Library Rare Books"),
    "U": ("大藏經補編", "Dazangjing Supplement"),
    "P": ("永樂北藏", "Yongle Northern Canon"),
    "J": ("嘉興藏", "Jiaxing Canon"),
    "L": ("乾隆大藏經", "Qianlong Canon"),
    "G": ("佛教大藏經", "Buddhist Canon"),
    "M": ("卍正藏經", "Man Zhengzang"),
    "N": ("南傳大藏經", "Pali Canon (Chinese)"),
    "ZS": ("正史佛教資料類編", "Official Histories"),
    "I": ("北朝佛教石刻拓片百品", "Stone Inscriptions"),
    "ZW": ("藏外佛教文獻", "Extra-canonical"),
    "B": ("大藏經補編", "Canon Supplement B"),
    "GA": ("中國佛寺志", "Chinese Temple Gazetteers"),
    "GB": ("中國佛寺志", "Chinese Temple Gazetteers B"),
    "Y": ("印順法師佛學著作集", "Yinshun Collection"),
    "LC": ("呂澂佛學著作集", "Lü Cheng Collection"),
    "W": ("藏外佛教文獻", "Extra-canonical W"),
}

# Dynasty mapping for common translator attributions
TRANSLATOR_DYNASTIES = {
    "後漢": "東漢",
    "吳": "三國",
    "曹魏": "三國",
    "西晉": "西晉",
    "東晉": "東晉",
    "前秦": "十六國",
    "後秦": "十六國",
    "北涼": "十六國",
    "劉宋": "南朝",
    "蕭齊": "南朝",
    "梁": "南朝",
    "陳": "南朝",
    "北魏": "北朝",
    "北齊": "北朝",
    "北周": "北朝",
    "隋": "隋",
    "唐": "唐",
    "五代": "五代",
    "宋": "宋",
    "遼": "遼",
    "金": "金",
    "元": "元",
    "明": "明",
    "清": "清",
    "民國": "民國",
    "後魏": "北朝",
    "日本": "日本",
}

CBETA_ONLINE_BASE = "https://cbetaonline.dila.edu.tw/zh/"


def parse_dynasty_translator(byline: str) -> tuple[str | None, str | None]:
    """Parse dynasty and translator from CBETA byline like '後秦 鳩摩羅什譯'."""
    if not byline:
        return None, None

    byline = byline.strip()

    for dynasty_key in sorted(TRANSLATOR_DYNASTIES.keys(), key=len, reverse=True):
        if byline.startswith(dynasty_key):
            dynasty = TRANSLATOR_DYNASTIES[dynasty_key]
            translator = byline[len(dynasty_key):].strip()
            if translator.endswith("譯"):
                translator = translator[:-1].strip()
            return dynasty, translator if translator else None

    translator = byline
    if translator.endswith("譯"):
        translator = translator[:-1].strip()
    return None, translator if translator else None
