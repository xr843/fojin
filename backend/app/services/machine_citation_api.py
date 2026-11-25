"""开放接口层用的引用组装：URN / CBETA 行首 → 完整机器可读引用；核验结果补行级位置。

与问答（chat）链路无关：chat 的引文补救也调 quote_lookup.verify_quote，这里只在开放的
/api/verify/quote 与 /api/citations/cite 上追加字段，问答的行为与耗时不变。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import TextNotFoundError, ValidationError
from app.models.text import BuddhistText
from app.schemas.verification import QuoteVerdict
from app.services.line_locate import locate_quote
from app.services.machine_citation import build_citation, license_for, normalize_line_ref, parse_line_head
from app.services.text import get_text_id_by_cbeta
from app.services.urn import (
    URNParseError,
    absolute_reader_url,
    build_urn,
    juan_for_line,
    parse_urn,
    reader_path,
    resolve_urn_full,
)

# 核验结果里最多给前几条命中补行号：每条要读一卷全文（有缓存），短句可能命中上百处
MAX_LOCATED_MATCHES = 3


async def _text_meta(db: AsyncSession, text_id: int) -> BuddhistText | None:
    return (await db.execute(select(BuddhistText).where(BuddhistText.id == text_id))).scalar_one_or_none()


def _line_urn(cbeta_id: str | None, juan: int | None, line_ref: str | None) -> str | None:
    return build_urn(cbeta_id, juan, f"p{line_ref}" if line_ref else None)


async def build_cite_response(db: AsyncSession, *, urn: str | None, ref: str | None, quote: str | None) -> dict:
    if not urn and not ref:
        raise ValidationError("需要 urn 或 ref（CBETA 行首）其中之一")

    text_id: int | None = None
    juan: int | None = None
    line_ref: str | None = None
    if ref:
        parsed_head = parse_line_head(ref)
        if not parsed_head:
            raise ValidationError(f"看不懂的 CBETA 行首：{ref}（应形如 T12n0374_p0450a12）")
        cbeta_id, line_ref = parsed_head
        text_id = await get_text_id_by_cbeta(db, cbeta_id)
        if text_id is None:
            raise TextNotFoundError(cbeta_id=cbeta_id)
        juan = await juan_for_line(db, text_id, line_ref, nearest=cbeta_id.startswith("T"))
    else:
        try:
            parsed = parse_urn(urn or "")
        except URNParseError as exc:
            raise ValidationError(str(exc)) from exc
        parsed, text_id, _ = await resolve_urn_full(db, parsed)
        if text_id is None:
            raise TextNotFoundError(cbeta_id=parsed.work_id)
        juan = parsed.juan
        line_ref = normalize_line_ref(parsed.anchor)

    bt = await _text_meta(db, text_id)
    if bt is None:
        raise TextNotFoundError(text_id=text_id)
    reader_url = absolute_reader_url(reader_path(text_id, juan, f"p{line_ref}" if line_ref and juan else None))
    return build_citation(
        cbeta_id=bt.cbeta_id,
        title=bt.title_zh,
        juan=juan,
        fascicle_count=bt.fascicle_count,
        line_ref=line_ref if juan else None,
        urn=_line_urn(bt.cbeta_id, juan, line_ref if juan else None),
        reader_url=reader_url,
        translator=bt.translator,
        dynasty=bt.dynasty,
        quote=quote,
    )


async def enrich_verdict(db: AsyncSession, verdict: QuoteVerdict) -> QuoteVerdict:
    """给开放核验接口的结果补：前几条命中的行号、行级 URN、跳到那一行并高亮的链接、可粘贴引用、许可。

    定位不到行（行号表没有、或标点异文导致找不到）就保持卷级，不报错。"""
    if not verdict.matches:
        return verdict
    needle = verdict.quote
    out = []
    for i, m in enumerate(verdict.matches):
        lic = license_for(m.cbeta_id)
        update: dict = {"license": lic["license"], "license_url": lic["license_url"], "attribution": lic["attribution"]}
        if i < MAX_LOCATED_MATCHES:
            located = await locate_quote(db, m.text_id, m.juan_num, needle)
            line_ref = normalize_line_ref(located[0]) if located else None
            reader_url = m.reader_url
            if located:
                url = absolute_reader_url(reader_path(m.text_id, m.juan_num, located[0]))
                reader_url = f"{url}&hl={located[1]}-{located[2]}" if url else reader_url
            bt = await _text_meta(db, m.text_id)
            cit = build_citation(
                cbeta_id=m.cbeta_id,
                title=m.title_zh or (bt.title_zh if bt else ""),
                juan=m.juan_num,
                fascicle_count=bt.fascicle_count if bt else None,
                line_ref=line_ref,
                urn=_line_urn(m.cbeta_id, m.juan_num, line_ref) or m.urn,
                reader_url=reader_url,
                translator=bt.translator if bt else None,
                dynasty=bt.dynasty if bt else None,
                quote=needle,
            )
            update |= {
                "line_ref": line_ref,
                "cbeta_line_head": cit["cbeta_line_head"],
                "line_urn": cit["urn"] if line_ref else None,
                "reader_url": reader_url,
                "citation": cit["plain"],
            }
        out.append(m.model_copy(update=update))
    return verdict.model_copy(update={"matches": out})
