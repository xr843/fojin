"""Schemas for /api/commentary — 一段经文，历代各家怎么注。

Agent-facing like the verification schemas: every claim is either resolvable
(URNs, reader URLs) or explicitly bounded (``truncated``, ``caveats``). The
corpus is known to be incomplete — roughly half of what a commentator actually
wrote is not aligned — so a response that reads as exhaustive would be a lie.
"""

from pydantic import BaseModel

__all__ = ["CommentaryHit", "CorpusInfo", "PassageCommentaries"]


class CommentaryHit(BaseModel):
    work: str
    title: str | None = None
    # A/B/C —— 该部注疏的质检档次（留出法准确率 ≥95% / 85–95% / 70–85%）。
    tier: str | None = None
    note: str
    anchor: str
    base_line: str
    # 这家注的是哪一句经 —— 一段里各家牒的句子不同，不给出来读者无从判断
    # 眼前这条是不是在回答他划的那句。
    base_text: str | None = None
    # 该注锚定的行是否落在读者划选范围内。False = 窗口边缘的兜底结果。
    on_selection: bool = True
    score: float
    # 同一部书的另一版本（牒句分布几乎重合），例如玄宗御注收在两部藏经里。
    # 只标不合并——藏掉一部 CBETA 书对要按版本查证的人更糟。
    same_as: str | None = None
    urn: str | None = None
    reader_url: str | None = None


class PassageCommentaries(BaseModel):
    query: str
    matched: bool
    base_work: str | None = None
    base_title: str | None = None
    base_urn: str | None = None
    base_reader_url: str | None = None
    passage: str | None = None
    line_from: str | None = None
    line_to: str | None = None
    commentaries: list[CommentaryHit] = []
    # 本段实际有几家 vs 返回了几家。截断时必须看得出来。
    total: int = 0
    truncated: bool = False
    # 没命中时一并给出可查的经 —— 覆盖面目前很窄，不说清楚调用方只会反复试错，
    # 而且会把「这部经没数据」误读成「这句话没人注过」。
    available_sutras: list[dict] = []
    caveats: list[str] = []


class CorpusInfo(BaseModel):
    """哪些经有经注对读数据 —— 问之前先知道能问什么。"""

    sutras: list[dict] = []
    caveats: list[str] = []
