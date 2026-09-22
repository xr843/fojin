"""经注对读端点 —— 一段经文，历代各家怎么注。

汉传注疏里「哪一段疏注哪一句经」这层关系，CBETA 对古代注疏基本没有标记；
这里提供的是把它抽出来之后的查询结果。数据本身不随本仓库发布（见
services/commentary 的说明），接口只回答问题。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.commentary import (
    CommentaryHit,
    CommentarySource,
    CommentarySourcePassage,
    CorpusInfo,
    PassageCommentaries,
)
from app.services import commentary as svc
from app.services.content import get_juan_line_anchors
from app.services.urn import absolute_reader_url, build_urn, reader_path

router = APIRouter(prefix="/commentary", tags=["commentary"])

_NO_DATA = (
    "本节点未安装经注对读数据包，因此没有可回答的经。这不是查询出错。"
)


# 行标 → 卷号。不要求精确命中，取同一页上最靠近的那条索引行。
#
# 为什么不精确匹配：2026-08-12 拿本包 4,230 条注疏锚点对生产索引量过一次，
# 精确命中只有 6.6%，而且是双峰的——大正藏那几部 99%，卍續藏几乎全 0%。
# 原因是 text_line_anchors 里 X 部的 <lb> 混着两个版本存（同一卷里 0448–0455
# 与 0523–0537 两套页码按字符位置交错），行的切法和对齐时用的那份不是同一套。
# 只认精确匹配的话，这个功能对 93% 的注疏等于没做。
#
# 限定同页，是为了不跨版本乱跳：一行的卷次必定等于同页另一行的卷次，而隔了
# 几十页的「最近邻」很可能是另一个版本的页码，那种猜法会把人送到错的卷。
# 同页找不到就退回书级——宁可少给，不给错的。
_JUAN_OF_LINE = sql_text(
    """
    SELECT DISTINCT ON (w.tid, w.ref)
           w.tid, w.ref, a.juan_num, a.line_ref
      FROM unnest(CAST(:tids AS int[]), CAST(:refs AS text[])) AS w(tid, ref)
      JOIN text_line_anchors a
        ON a.text_id = w.tid
       AND left(a.line_ref, 4) = left(w.ref, 4)
     ORDER BY w.tid, w.ref,
              (a.line_ref > w.ref),                                   -- 先取不越过目标的
              CASE WHEN a.line_ref <= w.ref THEN a.line_ref END DESC,  -- 其中最靠后的
              a.line_ref ASC                                           -- 都在目标之后就取最早的
    """
)


async def _locate(
    db: AsyncSession, targets: list[tuple[str, str | None]]
) -> dict[tuple[str, str | None], tuple[str | None, str | None]]:
    """(CBETA 书号, 行标) → (urn, 绝对阅读链接)，能落到行就落到行。

    两次查库，与结果条数无关：先把书号换成 text_id，再一次把所有行标换成卷号。

    退化是分层的，每层都比上一层保守：同页找不到索引行就只给卷级，书不在语料
    里就连链接都不给。注疏多半收在卍续藏、藏外等丛书里，未必都在 fojin 的语料
    内——查不到就老实留 None，不要拼一个点不开的链接。
    """
    if not targets:
        return {}

    want = {w: svc.to_cbeta_id(w) for w, _ in targets}
    ids = [c for c in want.values() if c]
    if not ids:
        return {t: (None, None) for t in targets}

    rows = (
        await db.execute(
            sql_text("SELECT cbeta_id, id FROM buddhist_texts WHERE cbeta_id = ANY(:ids)"),
            {"ids": ids},
        )
    ).fetchall()
    text_ids = {r[0]: r[1] for r in rows}

    # 行标 → (卷号, 该卷里最靠近的索引行)，一次问完。
    pairs = {
        (text_ids[want[w]], ref)
        for w, anchor in targets
        if want.get(w) in text_ids and (ref := svc.line_ref(anchor))
    }
    located: dict[tuple[int, str], tuple[int, str]] = {}
    if pairs:
        tids, refs = zip(*sorted(pairs), strict=True)
        for tid, ref, juan, near in await db.execute(
            _JUAN_OF_LINE, {"tids": list(tids), "refs": list(refs)}
        ):
            located[(tid, ref)] = (juan, near)

    out: dict[tuple[str, str | None], tuple[str | None, str | None]] = {}
    for work, anchor in targets:
        cbeta = want.get(work)
        if not cbeta:
            out[(work, anchor)] = (None, None)
            continue
        tid = text_ids.get(cbeta)
        ref = svc.line_ref(anchor)
        juan, near = located.get((tid, ref), (None, None)) if tid and ref else (None, None)
        # 滚动落点用索引里真有的那一行，不用 anchor 本身——指一行页面上不存在
        # 的行，阅读器什么也不会做，看起来就像链接坏了。
        # URN 里的锚点则跟规范走，带 p。
        at = f"p{near}" if near else None
        out[(work, anchor)] = (
            build_urn(cbeta, juan, at),
            absolute_reader_url(reader_path(tid, juan, at)) if tid else None,
        )
    return out


@router.get("/corpus", response_model=CorpusInfo)
async def corpus(db: AsyncSession = Depends(get_db)):
    """哪些经有经注对读数据。

    每条都带上 fojin 的 ``text_id``：调用方（抽屉）手里只有 text_id，没有它就得
    为每一条引文都试一次查询，而绝大多数引文并不在这个语料里。
    """
    sutras = svc.available()
    commentaries = svc.available_commentaries()
    want = {svc.to_cbeta_id(s["base_work"]) for s in sutras}
    want |= {c["cbeta_id"] for c in commentaries}
    ids: dict[str, int] = {}
    if cbeta_ids := [c for c in want if c]:
        ids = {
            r[0]: r[1]
            for r in (
                await db.execute(
                    sql_text("SELECT cbeta_id, id FROM buddhist_texts WHERE cbeta_id = ANY(:ids)"),
                    {"ids": cbeta_ids},
                )
            ).fetchall()
        }
    for s in sutras:
        s["text_id"] = ids.get(svc.to_cbeta_id(s["base_work"]))
    for c in commentaries:
        c["text_id"] = ids.get(c["cbeta_id"])
    return CorpusInfo(
        sutras=sutras,
        commentaries=commentaries,
        caveats=[_NO_DATA] if not sutras else [
            "对齐由程序产出、非人工校订；tier A/B/C 是该部注疏的质检档次。",
            "覆盖不完整：一部注疏实际所注，约一半没有被对齐出来。列出的注家"
            "不等于全部注家。",
        ],
    )


@router.get("/passage", response_model=PassageCommentaries)
async def passage(
    q: str = Query(..., min_length=2, max_length=200, description="一句经文"),
    limit: int = Query(svc.DEFAULT_LIMIT, ge=1, le=svc.MAX_LIMIT),
    db: AsyncSession = Depends(get_db),
):
    """这一段经文，历代各家怎么注。

    先在已装载的经里按内容定位（简繁通吃），再把锚点前后合成一「段」——注家
    把牒文锚在同一段的不同行上，按单行作答会把一段的注切碎。
    """
    pkgs = svc.packages()
    for pkg in pkgs:
        loc = pkg.locate(q)
        if not loc:
            continue
        core, i0, i1 = loc
        span, hits, total = pkg.passage(core, i0, i1, limit)
        base_work = pkg.meta["base_work"]
        # 经文侧锚到**读者划的第一行**，不是窗口的第一行——窗口向前多放了几行
        # 上文，锚在那里会把点进来的人送到他划的那句之前。
        base_key = (base_work, pkg.ids[i0] if i0 is not None else None)
        located = await _locate(
            db, [(h["work"], h["anchor"]) for h in hits] + [base_key]
        )
        base_urn, base_url = located.get(base_key, (None, None))
        return PassageCommentaries(
            query=q,
            matched=True,
            base_work=base_work,
            base_title=pkg.meta.get("base_title"),
            base_urn=base_urn,
            base_reader_url=base_url,
            passage="".join(pkg.text.get(x, "") for x in span),
            line_from=span[0] if span else None,
            line_to=span[-1] if span else None,
            commentaries=[
                CommentaryHit(
                    work=h["work"],
                    title=(pkg.comms.get(h["work"], {}) or {}).get("title"),
                    tier=(pkg.comms.get(h["work"], {}) or {}).get("tier"),
                    note=h["text"],
                    anchor=h["anchor"],
                    base_line=h["base_line"],
                    base_text=pkg.text.get(h["base_line"]),
                    on_selection=h["base_line"] in core,
                    score=h["score"],
                    same_as=(pkg.comms.get(h["work"], {}) or {}).get("same_as"),
                    urn=located.get((h["work"], h["anchor"]), (None, None))[0],
                    reader_url=located.get((h["work"], h["anchor"]), (None, None))[1],
                )
                for h in hits
            ],
            total=total,
            truncated=total > len(hits),
            caveats=[
                f"本段共 {total} 家注，返回前 {len(hits)} 家（按质检档次与置信度排序）。"
                if total > len(hits) else
                f"本段共 {total} 家注，已全部返回。",
                "覆盖不完整：一部注疏实际所注，约一半没有被对齐出来——列出的注家"
                "不等于全部注过这句的人。",
                "注文截到该注疏的下一处牒文为止，最多 4 行；要读全文请点 reader_url，"
                "它落在这条注所在的那一卷、同页最近的一行上（卍续藏诸书的行号"
                "索引与对齐所用的不是同一套，落点可能差一两行）。要引用请用 anchor，"
                "那是这条注真正的出处。",
                "原文出自 CBETA（CC BY-NC-SA 4.0，非营利使用）。",
            ],
        )
    return PassageCommentaries(
        query=q,
        matched=False,
        available_sutras=svc.available(),
        caveats=[_NO_DATA] if not pkgs else [
            "已装载的经里没有这一句 —— 见 available_sutras。注意区分两件事："
            "「这部经还没有经注数据」不等于「这句话没人注过」。",
            "定位是逐字的（简繁通吃，忽略标点），不做模糊匹配；引文有异文就会找不到。",
        ],
    )


_CHUNK = sql_text(
    "SELECT chunk_text FROM text_embeddings "
    "WHERE text_id = :tid AND juan_num = :juan AND chunk_index = :idx LIMIT 1"
)

# 同一卷可能有多语种正文；反查只在汉文原文上成立（行号索引也建在它上面）。
_CONTENT = sql_text(
    "SELECT content FROM text_contents WHERE text_id = :tid AND juan_num = :juan "
    "ORDER BY CASE WHEN lang = 'lzh' THEN 0 ELSE 1 END LIMIT 1"
)


def _locate_ignoring_whitespace(content: str, quote: str) -> tuple[int, int] | None:
    """引文块在本卷正文里的字符区间，忽略换行位置的差异。

    ``text_embeddings.chunk_text`` 与 ``text_contents.content`` 出自同一份正文，
    但**换行位置不同** —— CBETA 的硬换行在两处存法不一样。所以精确子串匹配
    ``content.find(quote)`` 会大面积假阴性：2026-09-22 在生产上抽 160 条俱舍系
    注疏引文实测，**95% 走到「定位不到」**，反查对二十分之十九的引文是哑的，
    而且失败是静默的（界面只说定位不到）。改成这里的忽略空白定位后，端点给出
    结果的比例 **5% → 36%**。

    返回的是**原文**偏移而非去空白后的偏移：下游 ``_span_lines`` 要拿它去比
    ``text_line_anchors`` 的 ``char_offset``，那套下标建在原文上。
    """
    kept = [i for i, ch in enumerate(content) if not ch.isspace()]
    flat = "".join(content[i] for i in kept)
    needle = "".join(ch for ch in quote if not ch.isspace())
    if not needle:
        return None
    at = flat.find(needle)
    if at < 0:
        return None
    return kept[at], kept[at + len(needle) - 1] + 1


def _span_lines(anchors: list[dict], start: int, end: int) -> tuple[str, str] | None:
    """字符区间 [start, end) 落在哪几行 —— 返回首尾行标。

    起点取**不越过它**的最后一个锚点：锚点标的是一行的起始位置，落在行中间的
    字属于上一个锚点那一行。终点同理，取仍在区间内的最后一行。
    """
    if not anchors:
        return None
    lo = None
    for a in anchors:
        if a["char_offset"] <= start:
            lo = a["line_ref"]
        else:
            break
    hi = lo
    for a in anchors:
        if a["char_offset"] < end:
            hi = a["line_ref"]
        else:
            break
    # 引文落在第一个锚点之前（卷首无 <lb> 的那几个字）时退到首行，不放弃整次查询。
    return (lo or anchors[0]["line_ref"], hi or anchors[0]["line_ref"])


@router.get("/source", response_model=CommentarySource)
async def source(
    text_id: int = Query(..., description="注疏在 fojin 的书 id"),
    juan: int = Query(..., ge=1),
    chunk_index: int | None = Query(None, ge=0, description="引文块序号；与 q 二选一"),
    q: str | None = Query(None, min_length=2, max_length=500, description="注文原文片段"),
    limit: int = Query(svc.DEFAULT_LIMIT, ge=1, le=svc.MAX_LIMIT),
    db: AsyncSession = Depends(get_db),
):
    """这段注文在解释哪一句 —— 正查的反方向。

    为什么要有它：读注疏的人最难的是不知道眼前这段在牒哪一句经/论。正查按经文
    行建索引，回答不了；而对齐数据本来两端都带行号，缺的只是反向索引。

    定位不靠文本匹配，靠行号：注文片段在本卷正文里的字符位置 → `text_line_anchors`
    的 CBETA 行标 → 包里锚在这几行上的对齐条目。包里只存了每条注的头 400 字，
    拿它做匹配会漏掉大半部书。
    """

    def empty(*caveats: str) -> CommentarySource:
        return CommentarySource(
            matched=False, text_id=text_id, juan=juan, chunk_index=chunk_index,
            caveats=list(caveats),
        )

    if not svc.packages():
        return empty(_NO_DATA)

    cbeta_id = (
        await db.execute(
            sql_text("SELECT cbeta_id FROM buddhist_texts WHERE id = :tid"), {"tid": text_id}
        )
    ).scalar()
    if not cbeta_id:
        return empty("没有这部书。")

    found = svc.find_commentary(cbeta_id)
    if not found:
        return empty(
            f"{cbeta_id} 不在经注对齐数据里，因此无法反查它注的是哪一句。"
            "这不等于它没有注释对象——可查的注疏见 /api/commentary/corpus 的 commentaries。"
        )
    pkg, work = found[0]

    quote = q
    if quote is None:
        if chunk_index is None:
            return empty("需要 chunk_index 或 q 之一，用来定位你在读哪一块注文。")
        quote = (
            await db.execute(_CHUNK, {"tid": text_id, "juan": juan, "idx": chunk_index})
        ).scalar()
        if not quote:
            return empty("这一卷里没有这个引文块。")

    content = (
        await db.execute(_CONTENT, {"tid": text_id, "juan": juan})
    ).scalar()
    if not content:
        return empty("这一卷没有正文。")
    located = _locate_ignoring_whitespace(content, quote)
    if located is None:
        # 引文块出自同一份正文，连忽略空白都找不到，通常意味着正文被重新导入过
        # （异文/换底本）。只差换行位置的那一类已由 _locate_ignoring_whitespace 兜住。
        return empty("这段注文在本卷正文里定位不到，无法换算成行号。")
    at, at_end = located

    anchors = await get_juan_line_anchors(db, text_id, juan)
    span = _span_lines(anchors, at, at_end)
    if not span:
        return empty("这一卷没有 CBETA 行号索引，无法反查。")
    line_from, line_to = span

    hits = pkg.source(work, line_from, line_to, limit)
    total = len(pkg.source(work, line_from, line_to, svc.MAX_LIMIT))
    base_work = pkg.meta["base_work"]
    located = await _locate(db, [(base_work, h["base_line"]) for h in hits])
    meta = pkg.comms.get(work) or {}

    def around(base_line: str) -> str:
        i = pkg.pos.get(base_line)
        if i is None:
            return pkg.text.get(base_line, "")
        return "".join(pkg.text.get(x, "") for x in pkg.ids[max(0, i - 1): i + 2])

    return CommentarySource(
        matched=bool(hits),
        text_id=text_id,
        juan=juan,
        chunk_index=chunk_index,
        work=work,
        work_title=meta.get("title"),
        tier=meta.get("tier"),
        line_from=line_from,
        line_to=line_to,
        base_work=base_work,
        base_title=pkg.meta.get("base_title"),
        passages=[
            CommentarySourcePassage(
                base_line=h["base_line"],
                base_text=around(h["base_line"]),
                note=h["text"],
                anchor=h["anchor"],
                score=h["score"],
                urn=located.get((base_work, h["base_line"]), (None, None))[0],
                reader_url=located.get((base_work, h["base_line"]), (None, None))[1],
            )
            for h in hits
        ],
        total=total,
        truncated=total > len(hits),
        caveats=[
            f"这块注文（{line_from}–{line_to}）牒到 {total} 句，返回 {len(hits)} 句。"
            if hits else
            "这块注文里没有对齐出来的牒文。覆盖不完整：一部注疏实际所注，约一半"
            "没有被对齐出来——「这里没有」不等于「这段没在解释任何一句」。",
            "base_text 给的是被牒那一行及前后各一行；要读上下文请点 reader_url。",
            "原文出自 CBETA（CC BY-NC-SA 4.0，非营利使用）。",
        ],
    )
