"""「这句经，佛真的说过吗？」——逐句核对与总结论（services/claim_check）。

verify_quote 本身另有测试；这里把它替换成按句查表的假实现，只测：切句、
总结论组合、出处去重、缓存。
"""

import pytest

from app.schemas.verification import ClosestMiss, DiffOp, QuoteMatch, QuoteVerdict
from app.services import claim_check
from app.services.claim_check import check_claim, split_clauses


def _match(cbeta, title, cls, text_id=1, juan=1):
    return QuoteMatch(text_id=text_id, cbeta_id=cbeta, title_zh=title, juan_num=juan, canon_class=cls)


def _verdict(q, matches, similarity=None):
    return QuoteVerdict(
        quote=q,
        normalised_quote=q,
        verbatim=bool(matches),
        bucket="exact" if matches else "absent",
        similarity=1.0 if matches else (similarity or 0.2),
        matches=matches,
    )


DIAMOND = _match("T0235", "金剛般若波羅蜜經", "sutra", 7)
DIAMOND_B = _match("T0236a", "金剛般若波羅蜜經", "sutra", 8)
COMMENTARY = _match("X0508", "金剛經闡說", "later", 900)
PLATFORM = _match("T2008", "六祖大師法寶壇經", "school", 70)
YUANWU = _match("T1997", "圓悟佛果禪師語錄", "school", 60)

LOTUS_CLOSE = ClosestMiss(
    text_id=297, juan_num=1, urn="fojin:cbeta/T0297.1", reader_url="https://fojin.app/texts/297/read?juan=1",
    similarity=0.9286, window_normalised="犹如莲花不着水亦如日月不着空",
    diff=[DiffOp(op="replace", quote="住", source="着")],
    cbeta_id="T0297", title_zh="普賢菩薩行願讚", canon_class="sutra",
)
NEAR = {"犹如莲花不著水，亦如日月不住空": LOTUS_CLOSE}

TABLE = {
    "一切有为法，如梦幻泡影": [DIAMOND, DIAMOND_B, COMMENTARY],
    "一切有为法": [DIAMOND, COMMENTARY],
    "如梦幻泡影": [DIAMOND],
    "菩提本无树，明镜亦非台": [YUANWU, PLATFORM],
}


@pytest.fixture(autouse=True)
def fake_lookup(monkeypatch):
    calls: list[str] = []

    async def fake_verify(db, es, quote, **kw):
        calls.append(quote)
        if quote in NEAR:
            close = NEAR[quote]
            return QuoteVerdict(
                quote=quote, normalised_quote=quote, verbatim=False, bucket="near_miss",
                similarity=close.similarity, closest=close,
            )
        return _verdict(quote, TABLE.get(quote, []))

    monkeypatch.setattr(claim_check, "verify_quote", fake_verify)
    claim_check._CACHE.clear()
    return calls


def test_split_clauses_on_chinese_and_ascii_punctuation():
    assert split_clauses("一切有为法，如梦幻泡影，看开便是福") == ["一切有为法", "如梦幻泡影", "看开便是福"]
    assert split_clauses("诸行无常;是生灭法!") == ["诸行无常", "是生灭法"]


def test_split_clauses_merges_fragments_too_short_to_look_up():
    # 「佛言」alone is two characters — below the 4-char lookup floor.
    assert split_clauses("佛言，一切众生，悉有佛性") == ["佛言一切众生", "悉有佛性"]


def test_split_clauses_caps_the_number_of_lookups():
    text = "，".join(f"第{i}句经文在此" for i in range(20))
    assert len(split_clauses(text)) == claim_check.MAX_CLAUSES


async def test_whole_quote_found_in_a_sutra():
    out = await check_claim(None, None, "一切有为法，如梦幻泡影")
    assert out.verdict == "sutra"
    assert len(out.segments) == 1 and out.segments[0].found
    # Two translations of the same sutra collapse to one title; at most three titles.
    titles = [s.title_zh for s in out.segments[0].sources]
    assert titles == ["金剛般若波羅蜜經", "金剛經闡說"]


async def test_found_only_outside_the_sutras():
    out = await check_claim(None, None, "菩提本无树，明镜亦非台")
    assert out.verdict == "not_sutra"
    assert out.source_class == "school"
    assert [s.cbeta_id for s in out.segments[0].sources] == ["T1997", "T2008"]


async def test_real_head_plus_invented_tail_is_partial(fake_lookup):
    out = await check_claim(None, None, "一切有为法，如梦幻泡影，看开便是福")
    assert out.verdict == "partial"
    assert [(s.text, s.found) for s in out.segments] == [
        ("一切有为法", True),
        ("如梦幻泡影", True),
        ("看开便是福", False),
    ]
    assert fake_lookup[0] == "一切有为法，如梦幻泡影，看开便是福"  # whole quote tried first


async def test_nothing_found_is_absent():
    out = await check_claim(None, None, "一切都是最好的安排")
    assert out.verdict == "absent"
    assert out.segments[0].found is False


async def test_results_are_cached(fake_lookup):
    await check_claim(None, None, "一切有为法，如梦幻泡影")
    n = len(fake_lookup)
    await check_claim(None, None, "一切有為法，如夢幻泡影")  # same after normalisation
    assert len(fake_lookup) == n


async def test_whole_quote_near_miss_is_a_variant_not_absent(fake_lookup):
    """Popular versions often differ from the canon by a character (莲花/蓮華,
    其土/其國). Saying "not in the canon" would be wrong; the line is there,
    worded slightly differently — and the reader should see the canon's words."""
    out = await check_claim(None, None, "犹如莲花不著水，亦如日月不住空")
    assert out.verdict == "variant"
    assert out.source_class == "sutra"
    assert len(out.segments) == 1  # whole near-miss is not split into clauses
    seg = out.segments[0]
    assert seg.found is False
    assert seg.close is not None and seg.close.title_zh == "普賢菩薩行願讚"
    assert fake_lookup == ["犹如莲花不著水，亦如日月不住空"]


# ── endpoint + rate limit ───────────────────────────────────────────────


def _app():
    from fastapi import FastAPI

    from app.api import verification
    from app.database import get_db

    app = FastAPI()
    app.include_router(verification.router, prefix="/api")

    async def no_db():
        yield None

    app.dependency_overrides[get_db] = no_db
    return app


async def _get(path):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as c:
        return await c.get(path)


async def test_claim_endpoint_returns_the_verdict(monkeypatch):
    from app.api import verification

    monkeypatch.setattr(verification, "get_es", lambda: None)
    resp = await _get("/api/verify/claim?q=" + "一切有为法，如梦幻泡影")
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "sutra"
    assert body["segments"][0]["sources"][0]["cbeta_id"] == "T0235"


async def test_claim_endpoint_rejects_too_short_and_too_long(monkeypatch):
    from app.api import verification

    monkeypatch.setattr(verification, "get_es", lambda: None)

    async def too_short(db, es, text):
        from app.services.quote_lookup import QuoteTooShortError

        raise QuoteTooShortError("short")

    monkeypatch.setattr(verification, "check_claim", too_short)
    assert (await _get("/api/verify/claim?q=佛")).status_code == 422
    assert (await _get("/api/verify/claim?q=" + "佛" * 201)).status_code == 422


def test_claim_and_image_endpoints_are_strict_rate_limited():
    from app.config import settings
    from app.core.rate_limit import STRICT_PATHS

    assert STRICT_PATHS["/api/verify/claim"] == settings.rate_limit_verify_claim
    assert STRICT_PATHS["/api/og/verify"] == settings.rate_limit_verify_claim
    # up to 1 + MAX_CLAUSES lookups per call — must sit well below the quote endpoint
    assert settings.rate_limit_verify_claim < settings.rate_limit_verify_quote
