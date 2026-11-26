"""问「某部经多少字 / 每卷多少字 / 几卷」时，把佛津收录文本的统计交给模型。

起因（2026-11-25 读者反馈）：读经页卷选择框里就有每卷字数，问答却答「手上没有 CBETA
逐卷字数清单」，还凭印象估「六七十万字」（实为约 59 万）。检索只取经文段落与辞典，
从来不看这份统计。

与引文链路的关系：
- 这里给的是**平台对电子文本的机器统计**，不是经文内容；块头写明不得写成
  【《经名》第N卷】出处标记，也不进 sources，引文核验与出处面板都不受影响；
- 只在问题明确问字数/卷数、且能从问题里认出部经名时才查，平常提问零开销。

口径：只数汉字（含扩展区与兼容汉字），不计标点、空白、校勘符号。读经页卷选择框里的
「字」是连标点一起数的 char_count，两者不同，块里两个数都给并说明。CBETA 官方「字數」
（如 T0279 593,143）与这里有千分之几的出入（缺字、组字处理不同），也照实告诉模型。
"""

import logging
import re

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.named_works import CARD_WORK_ALIASES, extract_named_works, resolve_named_work
from app.services.precise_retrieval import _to_traditional
from app.services.text_titles import strip_volume_range

logger = logging.getLogger(__name__)

# 问字数/卷数/篇幅才触发。繁简都写上（「數」「卷數」）。
# 「出处（第几卷）」是问引文在哪一卷，不是问这部经有几卷
_STATS_INTENT_RE = re.compile(
    r"字数|字數|多少字|几个字|幾個字|几字|幾字|(?<!第)(?:多少卷|几卷|幾卷)|卷数|卷數|篇幅|总字|總字"
)

MAX_WORKS = 4  # 同名多译本（华严三译）一起给
MAX_JUAN_LISTED = 120  # 超过就只给总数（大般若 600 卷之类）
MIN_TITLE_CHARS = 3  # 两字题名（「中論」）太容易误中，交给《》写法

_HAN_CLASS = r"一-鿿㐀-䶿豈-﫿\U00020000-\U0003ffff"


# 写作要求里的「字数300字左右」「篇幅受限」不是在问经的篇幅（2026-11-26 回放生产历史提问）
_WRITING_REQ_RE = re.compile(
    r"字数(?:在|不少于|不多于|不超过|不低于|约|控制在|要求)?\s*[\d一二三四五六七八九十百千万两]+|字左右|字数不限|篇幅(?:受限|所限|有限)"
)

# 不带「经/论」的简称（「80卷华严每卷字数」「俱舍几卷」）：从别名表派生，去掉末字「经」「论」后
# 至少两字才收。品名（普贤行愿品、普门品）不收——问的是一品，给整部经的数会被当成那一品的数。
_SHORT_ALIASES: dict[str, str] = {
    k[:-1]: k for k in CARD_WORK_ALIASES if k[-1] in "经论" and len(k) >= 3 and not k.endswith("品")
}
# 「华严」三译都给，再按问题里的卷数挑（别名表里的「华严经」只指 60/80 卷本，是卡片检索用的）
# 另加：通俗叫法与正式题名差得远、别名表又没有的（2026-11-26 用 22 部常问经论实测补齐）。
_EXTRA_ALIASES: dict[str, tuple[str, ...]] = {
    "华严": ("T0278", "T0279", "T0293"),
    "无量寿经": ("T0360",),
    "药师经": ("T0450",),
    "药师琉璃光如来本愿功德经": ("T0450",),
    "维摩经": ("T0475",),
    "楞伽经": ("T0670", "T0671", "T0672"),
    "中论": ("T1564",),
}

_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_JUAN_HINT_RE = re.compile(r"([\d]+|[一二两三四五六七八九十百]+)\s*卷")


def has_stats_intent(question: str) -> bool:
    q = question or ""
    return bool(_STATS_INTENT_RE.search(q)) and not _WRITING_REQ_RE.search(q)


def _cn_to_int(s: str) -> int | None:
    if s.isdigit():
        return int(s)
    total, cur = 0, 0
    for ch in s:
        if ch in _CN_NUM:
            cur = _CN_NUM[ch]
        elif ch == "十":
            total += (cur or 1) * 10
            cur = 0
        elif ch == "百":
            total += (cur or 1) * 100
            cur = 0
        else:
            return None
    return total + cur or None


def juan_hint(question: str) -> int | None:
    """「80卷华严」「八十卷本」→ 80；问「几卷」时没有数字，返回 None。"""
    m = _JUAN_HINT_RE.search(question or "")
    return _cn_to_int(m.group(1)) if m else None


def _drop_contained(titles: list[str]) -> list[str]:
    """「大方廣佛華嚴經」命中时，「華嚴經」「佛華嚴經」只是它的一截，去掉。"""
    return [t for t in titles if not any(t != o and t in o for o in titles)]


async def _resolve_ids(db: AsyncSession, question: str) -> list[int]:
    # 1) 《》点名的，走与卡片同一套精确解析（别名表 → 简转繁 → 异体字）
    ids: list[int] = []
    for name in extract_named_works(question):
        ids.extend(await resolve_named_work(db, name))
    if ids:
        return list(dict.fromkeys(ids))

    # 2) 问题里直接含完整题名（「80卷大方廣佛華嚴經共有多少字」）。取最长的那些，免得
    #    「華嚴經」这类短题名把一截当成另一部书。
    trad = _to_traditional(question)
    rows = (
        await db.execute(
            sql_text(
                "SELECT id, title_zh FROM buddhist_texts WHERE lang = 'lzh' AND has_content "
                "AND char_length(title_zh) >= :m AND (position(title_zh IN :q) > 0 OR position(title_zh IN :t) > 0 "
                "OR (title_zh LIKE '佛說%' AND char_length(title_zh) >= :m + 2 "
                "AND position(substr(title_zh, 3) IN :t) > 0)) "
                "ORDER BY cbeta_id LIMIT 40"
            ),
            {"m": MIN_TITLE_CHARS, "q": question, "t": trad},
        )
    ).all()
    keep = _drop_contained(list({r[1] for r in rows}))
    title_ids = [r[0] for r in rows if r[1] in keep]
    longest_title = max((len(t) for t in keep), default=0)

    # 3) 通称别名（「华严经」「俱舍论」）。问题里写了比别名更长的完整题名时以题名为准
    #    （「大方廣佛華嚴經」要连 40 卷本一起给，别名「华严经」只指 60/80 卷本）。
    for alias, ids_or_name in _alias_candidates():
        if alias in question or _to_traditional(alias) in question:
            if len(alias) >= longest_title:
                if isinstance(ids_or_name, tuple):
                    rows = await db.execute(
                        sql_text(
                            "SELECT id FROM buddhist_texts WHERE cbeta_id = ANY(:c) AND lang = 'lzh' "
                            "AND has_content ORDER BY cbeta_id"
                        ),
                        {"c": list(ids_or_name)},
                    )
                    return [r[0] for r in rows]
                return list(dict.fromkeys(await resolve_named_work(db, ids_or_name)))
            break
    return list(dict.fromkeys(title_ids))


def _alias_candidates() -> list[tuple[str, str | tuple[str, ...]]]:
    """(问题里要找的写法, 别名表键 或 cbeta_id 元组)，长的先试。品名不参与。"""
    cands: list[tuple[str, str | tuple[str, ...]]] = [(k, k) for k in CARD_WORK_ALIASES if not k.endswith("品")]
    cands += list(_SHORT_ALIASES.items()) + list(_EXTRA_ALIASES.items())
    return sorted(cands, key=lambda c: len(c[0]), reverse=True)


_PART_RE = re.compile(r"^([A-Z]+\d+)[a-z]$")


async def _expand_parts(db: AsyncSession, ids: list[int]) -> list[tuple[str, list[int]]]:
    """CBETA 跨册分段的经（T0220a…T0220o 共 15 段才是一部《大般若》）合成一部；
    返回 [(部经编号, [text_id…])]，按解析顺序。"""
    rows = (
        await db.execute(sql_text("SELECT id, cbeta_id FROM buddhist_texts WHERE id = ANY(:ids)"), {"ids": ids})
    ).all()
    cid = {r[0]: r[1] for r in rows}
    groups: dict[str, list[int]] = {}
    for tid in ids:
        c = cid.get(tid)
        if not c:
            continue
        m = _PART_RE.match(c)
        base = m.group(1) if m else c
        if base in groups:
            continue
        if m:
            parts = (
                await db.execute(
                    sql_text("SELECT id FROM buddhist_texts WHERE lang = 'lzh' AND cbeta_id ~ :pat ORDER BY cbeta_id"),
                    {"pat": f"^{base}[a-z]$"},
                )
            ).all()
            groups[base] = [r[0] for r in parts]
        else:
            groups[base] = [tid]
        if len(groups) >= MAX_WORKS:
            break
    return list(groups.items())


def format_stats_block(works: list[dict]) -> str:
    """works: [{cbeta_id, title, translator, dynasty, fascicle_count, han_total, raw_total, juans:[(n, han)]}]"""
    lines = [
        "【佛津收录文本统计】（平台对收录的 CBETA 电子文本的机器统计，**不是经文内容**："
        "引用这些数字时用普通叙述写明「据 CBETA 电子文本统计」，**不要**写成【《经名》第N卷】出处标记；"
        "数字须照抄，逐卷相加已算好，不要自行重算或估计。）",
        "口径：只计汉字，不计标点、空白与校勘符号；「含标点」指读经页卷选择框里显示的字数。"
        "CBETA 官方公布的字数因缺字、组字处理不同，可能与此相差千分之几。",
    ]
    for w in works:
        who = "".join(x for x in (w.get("dynasty"), w.get("translator")) if x)
        head = f"- 《{w['title']}》{w['cbeta_id']}" + (f"（{who}）" if who else "")
        head += f"，{w['n_juan']}卷：汉字共 {w['han_total']:,} 字；含标点 {w['raw_total']:,} 字。"
        expected = w.get("expected_juan")
        if expected and w["n_juan"] < expected:
            head += f"（注意：该经应有 {expected} 卷，佛津只收录了其中 {w['n_juan']} 卷，以上总数不全，须向用户说明。）"
        lines.append(head)
        if w["juans"] and len(w["juans"]) <= MAX_JUAN_LISTED:
            lines.append("  各卷汉字数：" + "；".join(f"卷{n} {c:,}" for n, c in w["juans"]))
    return "\n".join(lines)


async def lookup_work_stats(db: AsyncSession, question: str, prev_question: str | None = None) -> str:
    """问题问字数/卷数且认得出部经名 → 统计块；否则空串。出任何错都返回空串，不影响作答。

    追问（「那每卷多少字？」）本身没有经名时，从上一问里认经名。"""
    if not has_stats_intent(question):
        return ""
    try:
        async with db.begin_nested():
            ids = await _resolve_ids(db, question)
            if not ids and prev_question:
                ids = await _resolve_ids(db, prev_question)
            if not ids:
                return ""
            groups = await _expand_parts(db, ids)
            all_ids = [t for _, g in groups for t in g]
            meta = {
                r[0]: r
                for r in (
                    await db.execute(
                        sql_text(
                            "SELECT id, cbeta_id, title_zh, translator, dynasty, fascicle_count FROM buddhist_texts "
                            "WHERE id = ANY(:ids)"
                        ),
                        {"ids": all_ids},
                    )
                ).all()
            }
            rows = (
                await db.execute(
                    sql_text(
                        "SELECT text_id, juan_num, char_count, "
                        f"char_length(regexp_replace(content, '[^{_HAN_CLASS}]', '', 'g')) "
                        "FROM text_contents WHERE text_id = ANY(:ids) AND lang = 'lzh' "
                        "ORDER BY juan_num, text_id"
                    ),
                    {"ids": all_ids},
                )
            ).all()
    except Exception:
        logger.warning("work stats lookup failed, skipping", exc_info=True)
        return ""

    works = []
    for base, tids in groups:
        members = set(tids)
        wrows = [r for r in rows if r[0] in members]
        if not wrows or tids[0] not in meta:
            continue
        first = meta[tids[0]]
        expected = sum(int(meta[t][5] or 0) for t in tids if t in meta) or None
        works.append(
            {
                "cbeta_id": base,
                "title": strip_volume_range(first[2]),
                "translator": first[3],
                "dynasty": first[4],
                "n_juan": len(wrows),
                "expected_juan": expected,
                "han_total": sum(int(r[3] or 0) for r in wrows),
                "raw_total": sum(int(r[2] or 0) for r in wrows),
                "juans": [(r[1], int(r[3] or 0)) for r in wrows],
            }
        )
    # 「80卷华严」：同名多译本里只留卷数对得上的那一部
    hint = juan_hint(question)
    if hint and len(works) > 1 and any(w["n_juan"] == hint for w in works):
        works = [w for w in works if w["n_juan"] == hint]
    if not works:
        return ""
    logger.info("work stats injected: %s", ",".join(w["cbeta_id"] for w in works))
    return format_stats_block(works)
