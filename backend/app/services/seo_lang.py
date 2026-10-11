"""Per-language URL / tag helpers for crawler-facing HTML.

FoJin serves three UI languages from the same path, distinguished only by
``?lang=``. Search engines index each variant separately only if every variant
self-canonicalises and all of them cross-reference each other via hreflang —
see docs/superpowers/specs/2026-10-11-i18n-seo-design.md. The frontend mirrors
these rules in ``frontend/src/seo/langUrl.ts``; the two must produce
byte-identical URLs.
"""

import logging
from typing import Literal

from fastapi import Request
from opencc import OpenCC

logger = logging.getLogger(__name__)

SeoLang = Literal["zh", "zh-Hant", "en"]

# Suffix of the prebuilt frontend shell for each language (index{suffix}.html).
LANG_SHELL_SUFFIX: dict[str, str] = {"zh": "", "zh-Hant": ".zh-Hant", "en": ".en"}
_HTML_LANG = {"zh": "zh-Hans", "zh-Hant": "zh-Hant", "en": "en"}
_OG_LOCALE = {"zh": "zh_CN", "zh-Hant": "zh_TW", "en": "en_US"}
_t2s = OpenCC("t2s")


def resolve_lang(request: Request) -> SeoLang:
    """Only ``zh-Hant`` and ``en`` open a language variant; anything else is zh.

    Matched case-insensitively to agree with frontend/nginx.conf's
    ``map $arg_lang`` (nginx map string matching ignores case): ``?lang=EN``
    gets the English page, whose canonical is the lowercase ``?lang=en`` — so
    case variants consolidate instead of becoming separate pages. Junk values
    (``?lang=xyz``) render zh and canonicalise to the bare URL.
    """
    value = request.query_params.get("lang", "").lower()
    if value == "zh-hant":
        return "zh-Hant"
    if value == "en":
        return "en"
    return "zh"


def lang_url(base: str, path: str, lang: SeoLang) -> str:
    url = f"{base}{path}"
    return url if lang == "zh" else f"{url}?lang={lang}"


def hreflang_tags(base: str, path: str) -> str:
    pairs = [
        ("zh-Hans", lang_url(base, path, "zh")),
        ("zh-Hant", lang_url(base, path, "zh-Hant")),
        ("en", lang_url(base, path, "en")),
        ("x-default", lang_url(base, path, "zh")),
    ]
    return "\n  ".join(f'<link rel="alternate" hreflang="{code}" href="{href}" />' for code, href in pairs)


def html_lang(lang: SeoLang) -> str:
    return _HTML_LANG[lang]


def og_locale(lang: SeoLang) -> str:
    return _OG_LOCALE[lang]


def localize_title(title: str, lang: SeoLang) -> str:
    """Sutra titles are stored in traditional script (CBETA as-is).

    The simplified page shows「简体（繁體）」rather than replacing the title
    outright: ~10k text pages are already indexed under the traditional form,
    and keeping it avoids a site-wide title change while letting simplified
    queries match too.
    """
    if lang != "zh" or not title:
        return title
    try:
        simplified = _t2s.convert(title)
    except Exception as e:  # OpenCC failure must never break a page
        logger.warning("t2s conversion failed for %r: %s", title, e)
        return title
    return simplified if simplified == title else f"{simplified}（{title}）"
