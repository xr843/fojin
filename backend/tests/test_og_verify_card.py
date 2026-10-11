"""Result image for the /verify page (GET /api/og/verify?q=…).

The image carries fojin's name next to a verdict, so the verdict must always be
recomputed on the server — a query parameter can never set it, or anyone could
mint a「佛津：出自佛经」card for any sentence.
"""

import io

import pytest
from PIL import Image

from app.api import og
from app.schemas.verification import ClaimSegment, ClaimVerdict, ClosestMiss, QuoteMatch

DIAMOND = QuoteMatch(text_id=7, cbeta_id="T0235", title_zh="金剛般若波羅蜜經", juan_num=1, canon_class="sutra")
PLATFORM = QuoteMatch(text_id=70, cbeta_id="T2008", title_zh="六祖大師法寶壇經", juan_num=1, canon_class="school")

VERDICTS = {
    "一切有为法，如梦幻泡影": ClaimVerdict(
        query="", verdict="sutra", source_class="sutra",
        segments=[ClaimSegment(text="一切有为法，如梦幻泡影", found=True, sources=[DIAMOND])],
    ),
    "菩提本无树，明镜亦非台": ClaimVerdict(
        query="", verdict="not_sutra", source_class="school",
        segments=[ClaimSegment(text="菩提本无树，明镜亦非台", found=True, sources=[PLATFORM])],
    ),
    "一切有为法，看开便是福": ClaimVerdict(
        query="", verdict="partial",
        segments=[
            ClaimSegment(text="一切有为法", found=True, sources=[DIAMOND]),
            ClaimSegment(text="看开便是福", found=False),
        ],
    ),
    "犹如莲花不著水，亦如日月不住空": ClaimVerdict(
        query="", verdict="variant", source_class="sutra",
        segments=[ClaimSegment(
            text="犹如莲花不著水，亦如日月不住空", found=False,
            close=ClosestMiss(
                text_id=297, juan_num=1, similarity=0.93, window_normalised="犹如莲花不着水亦如日月不着空",
                cbeta_id="T0297", title_zh="普賢菩薩行願讚", canon_class="sutra",
            ),
        )],
    ),
    "一切都是最好的安排": ClaimVerdict(
        query="", verdict="absent", segments=[ClaimSegment(text="一切都是最好的安排", found=False)],
    ),
}


@pytest.fixture(autouse=True)
def fake_claim(monkeypatch):
    async def fake(db, es, text):
        return VERDICTS.get(text, VERDICTS["一切都是最好的安排"])

    monkeypatch.setattr(og, "check_claim", fake)
    monkeypatch.setattr(og, "get_es", lambda: None)


async def _get(path):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.database import get_db

    app = FastAPI()
    app.include_router(og.router, prefix="/api")

    async def no_db():
        yield None

    app.dependency_overrides[get_db] = no_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.get(path)


@pytest.mark.parametrize("q", list(VERDICTS))
async def test_every_verdict_renders_a_png_card(q):
    resp = await _get(f"/api/og/verify?q={q}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert "max-age=86400" in resp.headers["cache-control"]
    img = Image.open(io.BytesIO(resp.content))
    assert img.size == (og.CARD_WIDTH, og.CARD_HEIGHT)


async def test_a_verdict_in_the_url_is_ignored():
    plain = await _get("/api/og/verify?q=一切都是最好的安排")
    forged = await _get("/api/og/verify?q=一切都是最好的安排&verdict=sutra&source_class=sutra")
    assert forged.content == plain.content


async def test_the_badge_colour_follows_the_server_verdict():
    sutra = Image.open(io.BytesIO((await _get("/api/og/verify?q=一切有为法，如梦幻泡影")).content))
    absent = Image.open(io.BytesIO((await _get("/api/og/verify?q=一切都是最好的安排")).content))
    # Top accent bar is verdict-coloured.
    assert sutra.getpixel((10, 3)) != absent.getpixel((10, 3))


async def test_long_input_is_truncated_not_an_error():
    resp = await _get("/api/og/verify?q=" + "佛说" * 99)
    assert resp.status_code == 200


async def test_too_short_is_422(monkeypatch):
    from app.services.quote_lookup import QuoteTooShortError

    async def short(db, es, text):
        raise QuoteTooShortError("short")

    monkeypatch.setattr(og, "check_claim", short)
    assert (await _get("/api/og/verify?q=佛")).status_code == 422


def test_simplified_card_shows_titles_in_simplified_script():
    from app.api.og import _T2S

    assert _T2S.convert("金剛般若波羅蜜經") == "金刚般若波罗蜜经"


def test_near_miss_text_is_not_greyed_like_a_missing_clause():
    variant = VERDICTS["犹如莲花不著水，亦如日月不住空"]
    lines = og._layout_segments(variant, 1000)
    assert {colour for line in lines for _, colour in line} == {og._FOUND_INK}


async def test_search_outage_draws_no_card(monkeypatch):
    from app.services.quote_lookup import SearchUnavailableError

    async def down(db, es, text):
        raise SearchUnavailableError("es down")

    monkeypatch.setattr(og, "check_claim", down)
    assert (await _get("/api/og/verify?q=应无所住而生其心")).status_code == 503

