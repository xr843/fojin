"""``_inject_meta`` must rewrite og:* / twitter:* too, not just <title>.

Production regression: `/texts/13` served the correct `<title>` and canonical
but kept the SPA template's homepage Open Graph tags — so sharing any sutra to
WeChat/Twitter posted a card titled "佛津 FoJin — 问佛经，得到能核对原文的答案"
whose og:url was `https://fojin.app/`. Every share pointed readers at the
homepage instead of the thing being shared.

Why the existing suite missed it: `tests/test_seo_meta_injection.py` uses a
hand-written SHELL with no og:* tags at all, so there was nothing to leave
stale. These tests deliberately mirror the REAL `frontend/index.html` head.
"""

import re

from app.api.seo import _inject_meta

# Mirrors the real frontend/index.html head — the homepage values are exactly
# what leaked onto every text page before the fix.
SHELL = (
    "<!doctype html><html><head>"
    "<title>佛津 FoJin — 佛经 AI 问答，每句引用可点开核对原文</title>"
    '<meta name="description" content="向大藏经提问，小津用原文回答……" />'
    '<meta name="robots" content="index, follow" />'
    '<link rel="canonical" href="https://fojin.app/" />'
    '<meta property="og:type" content="website" />'
    '<meta property="og:title" content="佛津 FoJin — 问佛经，得到能核对原文的答案" />'
    '<meta property="og:description" content="AI 从大藏经原文作答……" />'
    '<meta property="og:url" content="https://fojin.app/" />'
    '<meta property="og:image" content="https://fojin.app/og-image.png" />'
    '<meta name="twitter:title" content="佛津 FoJin — 问佛经，得到能核对原文的答案" />'
    '<meta name="twitter:description" content="AI 从大藏经原文作答……" />'
    "</head><body></body></html>"
)

TITLE = "《大方廣佛華嚴經》 般若译 — 佛津 FoJin"
DESC = "《大方廣佛華嚴經》全文在线阅读，般若译。"
CANONICAL = "https://fojin.app/texts/13"


def _meta(html: str, prop: str) -> str | None:
    m = re.search(r'<meta\s+(?:property|name)="' + re.escape(prop) + r'"\s+content="([^"]*)"', html)
    return m.group(1) if m else None


def _patched() -> str:
    return _inject_meta(SHELL, title=TITLE, description=DESC, canonical_url=CANONICAL)


def test_og_url_points_at_this_page_not_the_homepage():
    """The regression that mattered: a shared sutra must not link to `/`."""
    assert _meta(_patched(), "og:url") == CANONICAL


def test_og_title_and_description_are_page_specific():
    html = _patched()
    assert _meta(html, "og:title") == TITLE
    assert _meta(html, "og:description") == DESC


def test_twitter_card_fields_follow_too():
    html = _patched()
    assert _meta(html, "twitter:title") == TITLE
    assert _meta(html, "twitter:description") == DESC


def test_og_image_is_left_alone():
    """There is no per-text image; the site-wide share card is correct here."""
    assert _meta(_patched(), "og:image") == "https://fojin.app/og-image.png"


def test_no_homepage_leftovers_anywhere_in_head():
    """Nothing may still advertise the homepage URL or its tagline."""
    html = _patched()
    head = html[: html.index("</head>")]
    assert 'content="https://fojin.app/"' not in head
    assert "问佛经，得到能核对原文的答案" not in head


def test_each_og_tag_appears_exactly_once():
    """Rewrite-in-place, not append — duplicated og:url is undefined behaviour."""
    html = _patched()
    for prop in ("og:title", "og:description", "og:url"):
        assert html.count(f'"{prop}"') == 1, prop


def test_values_are_escaped_in_og_tags_too():
    """og:* splices the same user-controlled strings; escaping must apply there."""
    html = _inject_meta(
        SHELL,
        title='evil" onload="x',
        description="a<b>c",
        canonical_url="https://fojin.app/texts/1",
    )
    assert 'onload="x' not in html
    assert "&quot;" in _meta(html, "og:title")
    assert "&lt;b&gt;" in _meta(html, "og:description")


def test_title_and_canonical_still_work():
    """Guard the pre-existing behaviour this change sits on top of."""
    html = _patched()
    assert f"<title>{TITLE}</title>" in html
    assert f'<link rel="canonical" href="{CANONICAL}" />' in html
