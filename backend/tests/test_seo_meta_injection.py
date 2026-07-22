"""Regression tests for HTML injection through the SEO meta-tag substitution.

``_inject_meta`` / ``_inject_share_qa_meta`` splice user-controlled strings
(shared-Q&A question/answer, text titles) into the SPA shell with
``re.sub(pattern, repl, html)``. ``re.sub`` *interprets escape sequences in
the replacement template*, so a payload can smuggle metacharacters past
``_escape_meta_value`` — which only escapes ``& " < >`` — and have them
materialise afterwards:

    ``\\074`` -> ``<``      ``\\076`` -> ``>``      ``\\042`` -> ``"``

``POST /api/share/qa`` is unauthenticated, so this was a stored HTML
injection on the production origin reachable by anyone.

A ``\\1`` in the same position raises ``re.error: invalid group reference``,
which 500s the share page permanently.
"""

import re

import pytest

from app.api.seo import _escape_meta_value, _inject_meta, _inject_share_qa_meta

SHELL = (
    "<!doctype html><html><head>"
    "<title>佛津</title>"
    '<meta name="description" content="orig" />'
    '<meta name="robots" content="index, follow" />'
    "</head><body></body></html>"
)

# Octal escapes only — contains no literal < > " so _escape_meta_value is a no-op.
OCTAL_PAYLOAD = r"\042\076\074meta http-equiv=\042refresh\042 content=\0420;url=https://evil.io\042\076"


def _meta(**overrides) -> dict[str, str]:
    base = {
        "title": "什么是空？",
        "description": "缘起性空",
        "canonical": "https://fojin.app/share/qa/abc123",
        "og_title": "什么是空？",
        "og_description": "缘起性空",
        "og_image": "https://fojin.app/api/og/share/qa/abc123",
    }
    base.update(overrides)
    return base


class TestEscapeMetaValue:
    def test_escapes_backslash_so_re_sub_cannot_reinterpret_it(self):
        assert "\\" not in _escape_meta_value(r"a\074b")

    def test_escapes_single_quote(self):
        assert "'" not in _escape_meta_value("it's")

    def test_still_escapes_the_original_four(self):
        assert _escape_meta_value('<a href="x">&') == "&lt;a href=&quot;x&quot;&gt;&amp;"


class TestInjectMetaOctalEscape:
    @pytest.mark.parametrize("field", ["title", "description", "canonical_url"])
    def test_octal_escapes_do_not_become_tags(self, field):
        kwargs = {
            "title": "safe",
            "description": "safe",
            "canonical_url": "https://fojin.app/x",
            field: OCTAL_PAYLOAD,
        }
        out = _inject_meta(SHELL, **kwargs)
        # The payload may appear as inert text, but must never form a tag.
        assert "<meta http-equiv=" not in out
        assert "refresh" not in out or "&#92;042refresh" in out

    def test_title_payload_cannot_close_the_title_element(self):
        out = _inject_meta(
            SHELL,
            title=r"\074/title\076\074meta http-equiv=\042refresh\042\076",
            description="safe",
            canonical_url="https://fojin.app/x",
        )
        # Exactly one closing </title> — the payload did not spawn another.
        assert out.count("</title>") == 1
        # "http-equiv" may survive as inert text inside <title>; what must not
        # exist is a tag built out of it.
        assert "<meta http-equiv" not in out


class TestInjectMetaGroupReference:
    """A backreference in the payload must not raise out of the injector."""

    @pytest.mark.parametrize("payload", [r"hi\1there", r"a\g<1>b", "trailing backslash\\"])
    def test_backreference_payload_does_not_raise(self, payload):
        out = _inject_meta(
            SHELL,
            title=payload,
            description=payload,
            canonical_url="https://fojin.app/x",
        )
        assert "<title>" in out


class TestInjectShareQaMeta:
    def test_octal_escape_in_og_description_does_not_become_a_tag(self):
        out = _inject_share_qa_meta(SHELL, _meta(og_description=OCTAL_PAYLOAD))
        assert "<meta http-equiv=" not in out

    def test_backreference_in_question_does_not_raise(self):
        out = _inject_share_qa_meta(SHELL, _meta(title=r"什么是\1空？"))
        assert 'property="og:title"' in out

    def test_legitimate_content_is_still_rendered(self):
        """The fix must not break normal Chinese/punctuation content."""
        out = _inject_share_qa_meta(SHELL, _meta(title="什么是「空」？", og_description="缘起性空 & 中道"))
        assert "什么是「空」？" in out
        assert "&amp;" in out  # the & was escaped, not dropped
        assert re.search(r'<meta property="og:title" content="[^"]*"', out)
