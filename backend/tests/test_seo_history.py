"""/history 分享卡片：按 ?p= / ?e= / ?r= / ?tour= 注入 title、og:*；参数无效退回总页；简体界面转简并校正「著」。"""

from unittest.mock import AsyncMock, patch

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api import seo_history as H

PEOPLE = {"people": [
    {"id": "A001583", "n": "慧能", "dy": "唐", "b": [638, 638], "d": [713, 713],
     "bio": "俗姓盧，著《壇經》。於曹溪寶林寺弘法。"},
]}  # fmt: skip
SHARE = {
    "events": {"huichang": {"y": 845, "s": "會昌法難", "t": "唐武宗毀拆天下寺院。", "q": "武宗會昌五年｜另一句"}},
    "tours": {"chan": {"title": "禪宗 · 東土六祖", "intro": "從菩提達磨到六祖慧能。"}},
}
TR = {"items": [{"y": 645, "t": "佛地經", "j": "一卷", "w": "玄奘"}, {"y": 649, "t": "說無垢稱經", "j": "六卷", "w": "玄奘"}]}
INDEX = (
    '<!doctype html><html lang="zh-CN"><head><title>佛津 FoJin</title>'
    '<meta name="description" content="generic" /><meta name="robots" content="index, follow" />'
    '<meta property="og:title" content="佛津 FoJin — 首页" /><meta property="og:description" content="g" />'
    '<meta property="og:url" content="https://fojin.app/" /><meta property="og:image" content="https://fojin.app/og-image.png" />'
    "</head><body><div id=\"root\"></div></body></html>"
)


async def _fake_data(name):
    return {"history-people.json": PEOPLE, "history-share.json": SHARE, "history-translations.json": TR}[name]


async def _fake_index(_suffix=""):
    return INDEX


@pytest_asyncio.fixture
async def client():
    with (
        patch("app.core.elasticsearch.init_es", new_callable=AsyncMock),
        patch("app.core.elasticsearch.close_es", new_callable=AsyncMock),
        patch("app.main.aioredis") as mock_redis_mod,
        patch.object(H, "_data", _fake_data),
        patch.object(H, "_fetch_index_html", _fake_index),
    ):
        mock_redis_mod.from_url.return_value = AsyncMock()
        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://fojin.app") as c:
            yield c


async def test_person_card_simplified_with_zhu_fixed(client):
    body = (await client.get("/history?p=A001583")).text
    assert '<meta property="og:title" content="慧能（638–713）· 中国佛教史长卷 — 佛津 FoJin" />' in body
    assert "著《坛经》" in body  # 转简后「着《」改回「著《」
    assert "/history?p=A001583" in body  # og:url / canonical 指向分享的这一页
    assert 'content="noindex, follow"' in body
    assert "og-image.png" in body  # 站点分享图不动


async def test_event_river_tour_cards(client):
    ev = (await client.get("/history?e=huichang&y=845")).text
    assert "公元 845 年 · 会昌法难 · 中国佛教史长卷" in ev
    assert "唐武宗毁拆天下寺院。「武宗会昌五年」" in ev
    rv = (await client.get("/history?r=645")).text
    assert "640–649 年译出的经" in rv and "《佛地经》、《说无垢称经》" in rv and "/history?r=640" in rv
    tr = (await client.get("/history?tour=chan&s=2")).text
    assert "禅宗 · 东土六祖 · 导览" in tr


async def test_unknown_or_missing_param_falls_back_to_indexable_base_page(client):
    for url in ("/history", "/history?p=nobody", "/history?e=x", "/history?r=abc"):
        body = (await client.get(url)).text
        assert "<title>中国佛教史长卷 — 佛津 FoJin</title>" in body, url
        assert 'content="index, follow"' in body, url


async def test_traditional_and_english_shells(client):
    assert "慧能（638–713）· 中國佛教史長卷" in (await client.get("/history?p=A001583&lang=zh-Hant")).text
    assert "Timeline of Chinese Buddhism" in (await client.get("/history?lang=en")).text
