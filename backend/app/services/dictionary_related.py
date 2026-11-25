"""问答回答下方的「相关词条」卡片（借鉴如是佛典 AI 问答，2026-11-25）。

与问答的生成、引文链路完全分开：
- 前端在回答结束后单独请求 ``/api/dictionary/related?q=<读者的问题>``，这里只读辞典表；
- 不改喂给模型的上下文（rag_retrieval._lookup_dictionary_terms 原样不动），所以回答内容与
  经文引文一个字都不受影响；
- 卡片明确标「词条」与辞典名，和回答里的经文出处分开显示，读者不会把辞典释义当成经文。

为什么要另做一套筛选、不直接用喂给模型的那份：那份是「宁多勿漏」的背景资料（前缀匹配、
不挑辞典），2026-11-25 用近 400 条真实提问实测命中 40%，但大量是「但是」「古往今来」这类
日常词命中 NTI 英文短释义、音义书的反切、经录条目、只有词头没有释义的空条目——原样做成
卡片会误导读者。这里只取：
- 中文释义类辞典（CARD_SOURCES，按权威与可读性排序）；
- 词头与问题里的词**完全相同**（繁简互通），不做前缀匹配；
- 去掉开头重复的词头后仍有像样释义的条目。
"""

import re

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.dictionary import DictionaryEntry
from app.models.source import DataSource
from app.services.rag_retrieval import _CJK_TERM_RE, _QUESTION_WORDS, _zh_variants

# 中文释义类辞典，越靠前越优先。外文辞典（Soothill / NTI / 梵巴藏）、音义书（可洪、慧琳、希麟、
# 翻梵語）、经录与提要（閱藏知津、禪宗典籍提要）、对照词表（五體清文鑑、四譯合璧）不做卡片。
CARD_SOURCES: tuple[str, ...] = (
    "foguang",  # 佛光大辭典
    "dila-dfb",  # 丁福保佛学大辞典
    "zhonghua-baike",  # 中華佛教百科全書
    "bs-changjianci",  # 佛學常見詞彙（陳義孝）
    "bs-agama",  # 阿含辭典（莊春江）
    "bs-faxiang",  # 法相辭典（朱芾煌）
    "weishi",  # 唯識名詞白話新解
    "abhidharma",  # 阿毗达磨辞典
    "tiantai",  # 天台教學辭典
    "dila-nanshanlu",  # 南山律学辞典
    "sanzang-fashu",  # 三藏法數
    "fanyi-mingyi",  # 翻譯名義集
    "fxcd-tongbian",  # 佛學次第統編
    "shishi-yaolan",  # 釋氏要覽
    "zuting-shiyuan",  # 祖庭事苑
    "suyu-foyuan",  # 俗語佛源
)
_RANK = {code: i for i, code in enumerate(CARD_SOURCES)}

MAX_CARDS = 4
MAX_PER_HEADWORD = 2
MAX_TERMS = 6
EXCERPT_CHARS = 90
MIN_EXCERPT_CHARS = 8

_WS_RE = re.compile(r"\s+")

# 太泛、做成卡片没有信息量的词头（繁体，与辞典词头同形；比对时问题里的词先转繁）。
# 来自 2026-11-25 近 400 条真实提问试跑：这些词在辞典里有条目，但读者问的从来不是它们。
GENERIC_HEADWORDS = frozenset(
    "什麼 甚麼 利益 翻譯 事迹 事跡 用心 但是 自在 一時 最勝 分別 世尊 如來 佛法 修行 成佛 "
    "佛教 佛陀 眾生 菩薩 原文 意思 問題 解釋 白話 經文 經中 所說 如是 一切 因緣 功德 "
    "方便 世間 我們 他們 自己 如何 為何 為什麼 可以 應該 是否 這個 那個 時候".split()
)


def extract_terms(question: str) -> list[str]:
    """从问题里取候选词：与喂给模型的辞典查询同一套切词（去掉「什么是」等问句词后取 2–8 字汉字串）。"""
    cleaned = _QUESTION_WORDS.sub(" ", question or "")
    seen: set[str] = set()
    terms: list[str] = []
    for t in _CJK_TERM_RE.findall(cleaned):
        if any(v in GENERIC_HEADWORDS for v in _zh_variants(t)):
            continue
        if t not in seen:
            seen.add(t)
            terms.append(t)
        if len(terms) >= MAX_TERMS:
            break
    return terms


def make_excerpt(headword: str, definition: str | None) -> str | None:
    """释义摘要：去掉开头重复的词头（中華佛教百科等首行就是词头），压空白，截断。
    剩下的不到 MIN_EXCERPT_CHARS 字（空条目、只写「見某某條」之类）返回 None。"""
    text = _WS_RE.sub(" ", definition or "").strip()
    for _ in range(2):
        if text.startswith(headword):
            text = text[len(headword) :].lstrip(" ：:，,。　")
    if len(text) < MIN_EXCERPT_CHARS:
        return None
    return text if len(text) <= EXCERPT_CHARS else text[:EXCERPT_CHARS] + "…"


async def related_terms(db: AsyncSession, question: str) -> list[dict]:
    terms = extract_terms(question)
    if not terms:
        return []
    variant_to_term: dict[str, int] = {}
    for i, term in enumerate(terms):
        for v in _zh_variants(term):
            variant_to_term.setdefault(v, i)

    rows = (
        (
            await db.execute(
                select(DictionaryEntry)
                .join(DataSource, DataSource.id == DictionaryEntry.source_id)
                .where(
                    or_(*[DictionaryEntry.headword == v for v in variant_to_term]),
                    DataSource.code.in_(CARD_SOURCES),
                )
                .options(joinedload(DictionaryEntry.source))
                .limit(200)
            )
        )
        .unique()
        .scalars()
        .all()
    )

    candidates = []
    for e in rows:
        excerpt = make_excerpt(e.headword, e.definition)
        if not excerpt:
            continue
        candidates.append((variant_to_term.get(e.headword, 99), _RANK.get(e.source.code, 99), e.id, e, excerpt))
    # 问题里先出现的词在前；同一个词按辞典优先级
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))

    cards: list[dict] = []
    per_head: dict[str, int] = {}
    seen_pair: set[tuple[str, str]] = set()
    for _, _, _, e, excerpt in candidates:
        key = (e.headword, e.source.code)
        if key in seen_pair or per_head.get(e.headword, 0) >= MAX_PER_HEADWORD:
            continue
        seen_pair.add(key)
        per_head[e.headword] = per_head.get(e.headword, 0) + 1
        cards.append(
            {
                "id": e.id,
                "headword": e.headword,
                "source_code": e.source.code,
                "source_name": e.source.name_zh,
                "excerpt": excerpt,
            }
        )
        if len(cards) >= MAX_CARDS:
            break
    return cards
