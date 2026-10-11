from starlette.requests import Request

from app.services.seo_lang import (
    LANG_SHELL_SUFFIX,
    hreflang_tags,
    html_lang,
    lang_url,
    localize_title,
    og_locale,
    resolve_lang,
)


def _req(qs: str = "") -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "query_string": qs.encode(), "headers": []})


def test_resolve_lang_only_accepts_two_values():
    assert resolve_lang(_req("lang=zh-Hant")) == "zh-Hant"
    assert resolve_lang(_req("lang=en")) == "en"
    for qs in ("", "lang=zh", "lang=xyz", "lang=english", "lang=zh-TW"):
        assert resolve_lang(_req(qs)) == "zh"


def test_resolve_lang_is_case_insensitive_like_nginx_map():
    # frontend/nginx.conf's `map $arg_lang` matches strings case-insensitively,
    # so /?lang=EN already gets the English shell; the backend must agree or the
    # raw HTML and the shell disagree for /texts/:id?lang=EN.
    assert resolve_lang(_req("lang=EN")) == "en"
    assert resolve_lang(_req("lang=zh-hant")) == "zh-Hant"
    assert resolve_lang(_req("lang=ZH-HANT")) == "zh-Hant"


def test_lang_url():
    b = "https://fojin.app"
    assert lang_url(b, "/texts/1", "zh") == "https://fojin.app/texts/1"
    assert lang_url(b, "/texts/1", "zh-Hant") == "https://fojin.app/texts/1?lang=zh-Hant"
    assert lang_url(b, "/", "en") == "https://fojin.app/?lang=en"


def test_hreflang_tags_has_four_alternates():
    tags = hreflang_tags("https://fojin.app", "/texts/1")
    assert '<link rel="alternate" hreflang="zh-Hans" href="https://fojin.app/texts/1" />' in tags
    assert '<link rel="alternate" hreflang="zh-Hant" href="https://fojin.app/texts/1?lang=zh-Hant" />' in tags
    assert '<link rel="alternate" hreflang="en" href="https://fojin.app/texts/1?lang=en" />' in tags
    assert '<link rel="alternate" hreflang="x-default" href="https://fojin.app/texts/1" />' in tags
    assert tags.count("<link") == 4


def test_html_lang_and_og_locale():
    assert [html_lang(x) for x in ("zh", "zh-Hant", "en")] == ["zh-Hans", "zh-Hant", "en"]
    assert [og_locale(x) for x in ("zh", "zh-Hant", "en")] == ["zh_CN", "zh_TW", "en_US"]


def test_localize_title_pairs_simplified_with_traditional():
    assert localize_title("般若波羅蜜多心經", "zh") == "般若波罗蜜多心经（般若波羅蜜多心經）"
    assert localize_title("般若波羅蜜多心經", "zh-Hant") == "般若波羅蜜多心經"
    assert localize_title("般若波羅蜜多心經", "en") == "般若波羅蜜多心經"


def test_localize_title_writes_identical_forms_once():
    # 简繁同形（「中論」转出来仍有差异，故取一个真正同形的词）
    assert localize_title("中阿含", "zh") == "中阿含"
    assert localize_title("", "zh") == ""


def test_shell_suffix():
    assert LANG_SHELL_SUFFIX == {"zh": "", "zh-Hant": ".zh-Hant", "en": ".en"}
