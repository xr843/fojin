from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.text import BuddhistText

# ── Canon (底本) derivation ────────────────────────────────────────
# Logic mirrors scripts/build_works.py:canon_from_cbeta_id so that
# the runtime API surface and the offline FRBR Work-spine builder
# agree on which canon a given cbeta_id maps to. Keep both in sync
# when adding a new prefix.

_CANON_LABELS_ZH: dict[str, str] = {
    "taisho": "大正藏",
    "xuzang": "卍续藏",
    "pali": "巴利三藏",
    "kangyur": "甘珠尔",
    "gretil": "梵文 GRETIL",
}

# 大正藏、卍续藏以外的 CBETA 各藏的显示名（简体）。
# 印順、太虛、呂澂、演培四套著作权不在 CBETA 的 CC 授权内，佛津不收，这里也不列。
_OTHER_CBETA_CANONS_ZH: dict[str, str] = {
    "A": "赵城金藏",
    "B": "大藏经补编",
    "C": "中华大藏经",
    "CC": "CBETA 选集",
    "D": "国图善本佛典",
    "F": "房山石经",
    "G": "佛教大藏经",
    "GA": "中国佛寺史志汇刊",
    "GB": "中国佛寺志丛刊",
    "I": "北朝佛教石刻拓片",
    "J": "嘉兴藏",
    "K": "高丽藏",
    "L": "乾隆藏",
    "M": "卍正藏",
    "N": "汉译南传大藏经",
    "P": "永乐北藏",
    "S": "宋藏遗珍",
    "U": "洪武南藏",
    "ZS": "正史佛教资料类编",
    "ZW": "藏外佛教文献",
}
# 嘉兴藏、南传沿用搜索分面里早就预留的码（services/search_facets.CANONS），其余为 cbeta_<藏号小写>。
_OTHER_CBETA_CANON_CODES: dict[str, str] = {
    k: {"J": "jiaxing", "N": "nanchuan"}.get(k, f"cbeta_{k.lower()}") for k in _OTHER_CBETA_CANONS_ZH
}
_CANON_LABELS_ZH.update({_OTHER_CBETA_CANON_CODES[k]: v for k, v in _OTHER_CBETA_CANONS_ZH.items()})


def canon_from_cbeta_id(cbeta_id: str | None) -> str | None:
    """Map a cbeta_id prefix to its canon code.

    T... → taisho, X... → xuzang, SC-... → pali, 84K-toh... → kangyur,
    GRETIL-... → gretil, VRI-... → pali. Unknown prefix → None.
    """
    if not cbeta_id:
        return None
    if cbeta_id.startswith("SC-"):
        return "pali"
    if cbeta_id.startswith("84K-toh"):
        return "kangyur"
    if cbeta_id.startswith("GRETIL-"):
        return "gretil"
    if cbeta_id.startswith("VRI-"):
        return "pali"
    from app.core.xml_parser import collection_of

    coll = collection_of(cbeta_id)
    if coll == "T":
        return "taisho"
    if coll == "X":
        return "xuzang"
    if coll in _OTHER_CBETA_CANON_CODES:
        return _OTHER_CBETA_CANON_CODES[coll]
    return None


def canon_label_zh(canon: str | None) -> str | None:
    """Return the Chinese display label for a canon code, or None."""
    if not canon:
        return None
    return _CANON_LABELS_ZH.get(canon)


async def get_text_by_id(session: AsyncSession, text_id: int) -> BuddhistText | None:
    result = await session.execute(
        select(BuddhistText).where(BuddhistText.id == text_id)
    )
    return result.scalar_one_or_none()


async def get_text_id_by_cbeta(session: AsyncSession, cbeta_id: str) -> int | None:
    """Resolve a CBETA ID (e.g. ``T0278``) to the lowest internal text id.

    cbeta_id 在 buddhist_texts 上为 unique，但若未来同一编号跨数据源出现，
    取 id 最小那条以保持可预测的跳转目标。"""
    result = await session.execute(
        select(BuddhistText.id)
        .where(BuddhistText.cbeta_id == cbeta_id)
        .order_by(BuddhistText.id.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_text_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(BuddhistText.id)))
    return result.scalar() or 0


async def get_all_text_ids_with_dates(session: AsyncSession) -> list[tuple[int, str]]:
    """Return (id, created_at_date_str) for all texts, ordered by id.

    CBETA 的现代附文（补遗编号，见 app.core.xml_parser.is_front_matter）不进站点地图。
    """
    from app.core.xml_parser import FRONT_MATTER_ID_RE

    result = await session.execute(
        select(BuddhistText.id, BuddhistText.created_at)
        .where(~BuddhistText.cbeta_id.op("~")(FRONT_MATTER_ID_RE.pattern))
        .order_by(BuddhistText.id)
    )
    return [(row[0], row[1].strftime("%Y-%m-%d")) for row in result.all()]


# ── 读经页：按大正藏编号区间列经目 ────────────────────────────────
TAISHO_MAX_NO = 2920
TAISHO_MAX_SPAN = 700  # 最大的部（密教部）573 个编号；限制单次查询规模


async def browse_taisho(session: AsyncSession, from_no: int, to_no: int, catalog_only: bool = False) -> list[dict]:
    """大正藏 T{from_no}..T{to_no}（含两端、含 a/b 变体）里有正文的经目，按编号排序。

    catalog_only=True 时反过来只列**没有正文**的目录条目：第 56–84 册（日本撰述）
    CBETA 未收，库里只有目录，读经页据此列经目并外链 SAT。

    cbeta_id 是四位补零（T0001、T0235b），所以编号区间可以直接用字符串比较表达，
    不依赖 Postgres 正则（测试用的 SQLite 也能跑）。
    """
    lo, hi = f"T{from_no:04d}", f"T{to_no + 1:04d}"
    rows = (
        await session.execute(
            select(
                BuddhistText.id,
                BuddhistText.cbeta_id,
                BuddhistText.title_zh,
                BuddhistText.translator,
                BuddhistText.dynasty,
                BuddhistText.fascicle_count,
            )
            .where(
                BuddhistText.cbeta_id >= lo,
                BuddhistText.cbeta_id < hi,
                BuddhistText.has_content.is_(not catalog_only),
            )
            .order_by(BuddhistText.cbeta_id)
        )
    ).all()
    return [
        {
            "id": r.id,
            "cbeta_id": r.cbeta_id,
            "title_zh": r.title_zh,
            "translator": r.translator,
            "dynasty": r.dynasty,
            "fascicle_count": r.fascicle_count,
        }
        for r in rows
    ]
