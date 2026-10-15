"""卡片题点名的经论 → buddhist_texts.id，供检索给每部点名经论保底一个上下文槽。

为什么需要：卡片的检索只用显示文字（「《念处经》四念处如何实修？」），而模板里
点名的经论（《中阿含经·念处经》《清净道论》……）向量检索多半带不回来——200 张
卡片里 119 张一部都没带回，其中很多语料库里其实有（2026-10-15 审计）。模型拿着
「每条附原典引用」的要求却没有原文，只能在思考里反复权衡怎么如实转述，首字因此
慢、答案也只能转述。

题名解析只做**精确匹配**（别名表 → 简转繁 → 异体字 → 「佛說」前缀），不做前缀/
模糊匹配：实测前缀匹配会把《俱舍论》解析成《俱舍論記》、《法华玄义》解析成
《法華玄義釋籤》——注疏冒充本典，比带不回来更糟。解析不到就跳过，退回原检索。
"""

import logging
import re

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.precise_retrieval import _to_traditional

logger = logging.getLogger(__name__)

# 一张卡片最多给几部点名经论保底（其余上下文仍归原检索）。
MAX_NAMED_WORKS = 3
# 一部经论最多解析出几个译本/分册一起参与范围检索（华严三译、大般若三册）。
_MAX_IDS_PER_WORK = 6

_NAME_RE = re.compile(r"《([^》]{2,40})》")
# 《中阿含经·念处经》《华严经·入法界品》：取「·」前的部经名。品名/子经不单独成书，
# 范围检索在整部经里按问题语义取段，自然落到那一品。
_PART_SEP_RE = re.compile(r"[·・]")

# 简写/通称 → cbeta_id。只收「简转繁精确匹配解析不到或会解析错」的条目；全部在
# 生产库核对过题名（2026-10-16）。
CARD_WORK_ALIASES: dict[str, tuple[str, ...]] = {
    "心经": ("T0251",),
    "般若波罗蜜多心经": ("T0251",),
    "金刚经": ("T0235",),
    "法华经": ("T0262",),
    "妙法莲华经": ("T0262",),
    "坛经": ("T2008",),
    "六祖坛经": ("T2008",),
    "楞严经": ("T0945",),
    "大佛顶首楞严经": ("T0945",),
    "圆觉经": ("T0842",),
    "地藏经": ("T0412",),
    "阿弥陀经": ("T0366",),
    "观无量寿佛经": ("T0365",),
    "四十二章经": ("T0784",),
    # 「维摩诘经」精确匹配会落到支谦译《佛說維摩詰經》，通行的是罗什译本。
    "维摩诘经": ("T0475",),
    # 「涅槃经」精确匹配会带上《長阿含》的小乘《大般涅槃經》(T0007)；卡片问的是大乘涅槃。
    "涅槃经": ("T0374", "T0375"),
    "大般涅槃经": ("T0374", "T0375"),
    "华严经": ("T0278", "T0279"),
    "普贤行愿品": ("T0293",),
    "大般若经": ("T0220a", "T0220b", "T0220c"),
    "大般若波罗蜜多经": ("T0220a", "T0220b", "T0220c"),
    "俱舍论": ("T1558",),
    "阿毗达磨俱舍论": ("T1558",),
    "大毗婆沙论": ("T1545",),
    "法华玄义": ("T1716",),
    "法华玄赞": ("T1723",),
    "大慈恩寺三藏法师传": ("T2053",),
    "佛国记": ("T2085",),
    "佛所行赞": ("T0192",),
    "大集经": ("T0397",),
    "胜鬘经": ("T0353",),
    "如来藏经": ("T0666",),
    "安般守意经": ("T0602",),
    "光赞般若经": ("T0222",),
    "大品般若": ("T0223",),
    "小品般若": ("T0227",),
    "临济录": ("T1985",),
    "敕修百丈清规": ("T2025",),
    "华严义海百门": ("T1875",),
    "观经疏": ("T1753",),
    "观经四帖疏": ("T1753",),
    "歎异抄": ("T2661",),
}

# OpenCC s2t 不碰的异体字：大藏经题名用「毘/呪/註/讚/勅」。
_VARIANT_TABLE = str.maketrans({"毗": "毘", "咒": "呪", "注": "註", "赞": "讚", "敕": "勅"})

_cache: dict[str, tuple[int, ...]] = {}


def extract_named_works(template: str) -> list[str]:
    """模板里《》点名的部经名，按出现顺序去重。"""
    names: list[str] = []
    for raw in _NAME_RE.findall(template or ""):
        head = _PART_SEP_RE.split(raw)[0].strip()
        if len(head) >= 2 and head not in names:
            names.append(head)
    return names


async def resolve_named_work(db: AsyncSession, name: str) -> tuple[int, ...]:
    """部经名 → 有正文的汉文 buddhist_texts.id（可能多个译本）；解析不到返回空元组。

    结果按进程缓存（含解析失败），题名表是静态的。"""
    if name in _cache:
        return _cache[name]
    ids: tuple[int, ...] = ()
    if name in CARD_WORK_ALIASES:
        rows = await db.execute(
            sql_text(
                "SELECT id FROM buddhist_texts WHERE cbeta_id = ANY(:c) AND lang = 'lzh' "
                "AND has_content ORDER BY cbeta_id"
            ),
            {"c": list(CARD_WORK_ALIASES[name])},
        )
        ids = tuple(r[0] for r in rows)
    else:
        trad = _to_traditional(name)
        candidates = list(dict.fromkeys([trad, trad.translate(_VARIANT_TABLE), "佛說" + trad]))
        for cand in candidates:
            rows = await db.execute(
                sql_text(
                    "SELECT id FROM buddhist_texts WHERE title_zh = :t AND lang = 'lzh' "
                    "AND has_content ORDER BY cbeta_id LIMIT :n"
                ),
                {"t": cand, "n": _MAX_IDS_PER_WORK},
            )
            ids = tuple(r[0] for r in rows)
            if ids:
                break
    _cache[name] = ids
    return ids
