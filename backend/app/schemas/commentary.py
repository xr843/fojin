"""Schemas for /api/commentary — 一段经文，历代各家怎么注。

Agent-facing like the verification schemas: every claim is either resolvable
(URNs, reader URLs) or explicitly bounded (``truncated``, ``caveats``). The
corpus is known to be incomplete — roughly half of what a commentator actually
wrote is not aligned — so a response that reads as exhaustive would be a lie.
"""

from pydantic import BaseModel

__all__ = [
    "CommentaryHit",
    "CommentarySource",
    "CommentarySourcePassage",
    "CorpusInfo",
    "PassageCommentaries",
]


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


class CommentarySourcePassage(BaseModel):
    """一段注文牒到的一句经/论。"""

    base_line: str
    # 被牒的那一行及其前后各一行 —— CBETA 一行才十来个字，单给一行多半是半句话。
    base_text: str | None = None
    note: str
    anchor: str
    score: float
    urn: str | None = None
    reader_url: str | None = None


class CommentarySource(BaseModel):
    """这段注文在解释哪一句 —— 正查（经文→各家注）的反方向。"""

    matched: bool
    text_id: int
    juan: int
    chunk_index: int | None = None
    # 注疏侧：这块注文是谁的、落在它自己书里的哪几行。
    work: str | None = None
    work_title: str | None = None
    tier: str | None = None
    line_from: str | None = None
    line_to: str | None = None
    # 经论侧：它注的是哪一部。
    base_work: str | None = None
    base_title: str | None = None
    passages: list[CommentarySourcePassage] = []
    total: int = 0
    truncated: bool = False
    caveats: list[str] = []


class CorpusInfo(BaseModel):
    """哪些经有经注对读数据 —— 问之前先知道能问什么。"""

    sutras: list[dict] = []
    # 哪些注疏可以反查（fojin 书号），抽屉据此决定要不要问。放在这里是为了让
    # 前端一次取到、就地判断，而不是每开一条引文都去试一次反查接口。
    commentaries: list[dict] = []
    caveats: list[str] = []
