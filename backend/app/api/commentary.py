"""经注对读端点 —— 一段经文，历代各家怎么注。

汉传注疏里「哪一段疏注哪一句经」这层关系，CBETA 对古代注疏基本没有标记；
这里提供的是把它抽出来之后的查询结果。数据本身不随本仓库发布（见
services/commentary 的说明），接口只回答问题。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.commentary import CommentaryHit, CorpusInfo, PassageCommentaries
from app.services import commentary as svc
from app.services.urn import absolute_reader_url, build_urn, reader_path

router = APIRouter(prefix="/commentary", tags=["commentary"])

_NO_DATA = (
    "本节点未安装经注对读数据包，因此没有可回答的经。这不是查询出错。"
)


async def _reader_urls(db: AsyncSession, work_ids: list[str]) -> dict[str, tuple]:
    """CBETA 书号 → (urn, 绝对阅读链接)。一次查库，查不到的留空。

    注疏多半收在卍续藏、藏外等丛书里，未必都在 fojin 的语料内——查不到就
    老实留 None，不要拼一个点不开的链接。
    """
    want = {w: svc.to_cbeta_id(w) for w in work_ids}
    ids = [c for c in want.values() if c]
    if not ids:
        return {}
    rows = (
        await db.execute(
            sql_text("SELECT cbeta_id, id FROM buddhist_texts WHERE cbeta_id = ANY(:ids)"),
            {"ids": ids},
        )
    ).fetchall()
    by_cbeta = {r[0]: r[1] for r in rows}
    out = {}
    for w, c in want.items():
        tid = by_cbeta.get(c)
        out[w] = (
            build_urn(c) if c else None,
            absolute_reader_url(reader_path(tid)) if tid else None,
        )
    return out


@router.get("/corpus", response_model=CorpusInfo)
async def corpus():
    """哪些经有经注对读数据。"""
    sutras = svc.available()
    return CorpusInfo(
        sutras=sutras,
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
        line = pkg.find(q)
        if not line:
            continue
        span, hits, total = pkg.passage(line, limit)
        urls = await _reader_urls(db, [h["work"] for h in hits])
        base_cbeta = svc.to_cbeta_id(pkg.meta["base_work"])
        base_urls = await _reader_urls(db, [pkg.meta["base_work"]])
        return PassageCommentaries(
            query=q,
            matched=True,
            base_work=pkg.meta["base_work"],
            base_title=pkg.meta.get("base_title"),
            base_urn=build_urn(base_cbeta) if base_cbeta else None,
            base_reader_url=base_urls.get(pkg.meta["base_work"], (None, None))[1],
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
                    score=h["score"],
                    same_as=(pkg.comms.get(h["work"], {}) or {}).get("same_as"),
                    urn=urls.get(h["work"], (None, None))[0],
                    reader_url=urls.get(h["work"], (None, None))[1],
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
                "注文截到该注疏的下一处牒文为止，最多 4 行；要读全文请循 anchor 回原书。",
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
