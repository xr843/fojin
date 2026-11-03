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
    if cbeta_id.startswith("T"):
        return "taisho"
    if cbeta_id.startswith("X"):
        return "xuzang"
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
    """Return (id, created_at_date_str) for all texts, ordered by id."""
    result = await session.execute(
        select(BuddhistText.id, BuddhistText.created_at).order_by(BuddhistText.id)
    )
    return [(row[0], row[1].strftime("%Y-%m-%d")) for row in result.all()]


# ── 读经页：按大正藏编号区间列经目 ────────────────────────────────
TAISHO_MAX_NO = 2920
TAISHO_MAX_SPAN = 700  # 最大的部（密教部）573 个编号；限制单次查询规模


async def browse_taisho(session: AsyncSession, from_no: int, to_no: int) -> list[dict]:
    """大正藏 T{from_no}..T{to_no}（含两端、含 a/b 变体）里有正文的经目，按编号排序。

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
                BuddhistText.has_content.is_(True),
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
