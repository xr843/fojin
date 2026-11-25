"""Shared constants and utilities for import scripts."""

# CBETA catalog categories mapping
CATEGORIES = {
    # 名称取自各藏 XML 表头 <title level="s">；T/X 沿用库里已有的写法。
    "T": ("大正藏", "Taishō"),
    "X": ("卍新纂續藏經", "Xuzangjing"),
    "A": ("趙城金藏", "Zhaocheng Jinzang"),
    "B": ("大藏經補編", "Dazangjing Bubian"),
    "C": ("中華大藏經", "Zhonghua Dazangjing"),
    "CC": ("CBETA 選集", "CBETA Selections"),
    "D": ("國家圖書館善本佛典", "National Central Library Rare Books"),
    "F": ("房山石經", "Fangshan Stone Sutras"),
    "G": ("佛教大藏經", "Fojiao Dazangjing"),
    "GA": ("中國佛寺史志彙刊", "Chinese Temple Gazetteers (Huikan)"),
    "GB": ("中國佛寺志叢刊", "Chinese Temple Gazetteers (Congkan)"),
    "I": ("北朝佛教石刻拓片百品", "Northern Dynasties Stone Inscriptions"),
    "J": ("嘉興大藏經", "Jiaxing Canon"),
    "K": ("高麗大藏經", "Goryeo Canon"),
    "L": ("乾隆大藏經", "Qianlong Canon"),
    "M": ("卍正藏經", "Manji Zhengzang"),
    "N": ("漢譯南傳大藏經", "Chinese Translation of the Pali Canon"),
    "P": ("永樂北藏", "Yongle Northern Canon"),
    "S": ("宋藏遺珍", "Songzang Yizhen"),
    "U": ("洪武南藏", "Hongwu Southern Canon"),
    "ZS": ("正史佛教資料類編", "Buddhist Materials in the Official Histories"),
    "ZW": ("藏外佛教文獻", "Extra-canonical Buddhist Texts"),
    # 下面四套著作权不在 CBETA 的 CC 授权内，佛津不收（见 NOTICE），只留名称以便识别。
    "Y": ("印順法師佛學著作集", "Yinshun Collection"),
    "TX": ("太虛大師全書", "Taixu Collection"),
    "LC": ("呂澂佛學著作集", "Lü Cheng Collection"),
    "YP": ("演培法師全集", "Yanpei Collection"),
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
