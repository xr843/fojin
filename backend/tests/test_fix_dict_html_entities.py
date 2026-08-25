"""Numeric character references leaked into dictionary_entries as literal text.

Prod 2026-07-21: 2,463 headwords + 7,663 definitions across 一切經音義（慧琳音義）
and 續一切經音義（希麟）read like ``&#X4E98;以`` instead of ``亘以``.

Cause: ``import_buddhaspace.py::_strip_html`` hand-rolled entity decoding for five
named entities only. Its ``&amp;`` → ``&`` pass runs first, so a source ``&amp;#X4E98;``
is turned INTO the literal ``&#X4E98;`` and then never decoded — the importer
manufactures the bad string itself.

These junk headwords each generate a /dict/ page that crawlers index, and every
one costs a reverse-index lookup (see test_seo_dict_reverse_index.py).

We decode ONLY numeric references. Named entities (``&amp;`` etc.) are left alone
so the backfill can never rewrite a legitimate ``&`` in a definition body.
"""

import pytest
from scripts.fix_dict_html_entities import SELECT_SQL, decode_entities, decode_numeric_entities


def test_decodes_uppercase_hex_reference():
    # The exact shape found in prod.
    assert decode_numeric_entities("&#X4E98;以") == "亘以"
    assert decode_numeric_entities("&#X4EBE;喪") == "亾喪"


def test_decodes_lowercase_hex_and_decimal():
    assert decode_numeric_entities("&#x4E98;以") == "亘以"
    assert decode_numeric_entities("&#20120;") == "亘"  # 0x4E98 == 20120


def test_decodes_multiple_references_in_one_string():
    # 63 prod headwords carry two references, one carries three.
    assert decode_numeric_entities("&#X4E98;和&#X4EBE;") == "亘和亾"


def test_leaves_named_entities_alone():
    """Conservative on purpose: a definition body may legitimately contain '&'.

    Decoding named entities would let the backfill rewrite text that was never
    broken, which is not what this migration is for.
    """
    assert decode_numeric_entities("A &amp; B") == "A &amp; B"
    assert decode_numeric_entities("&nbsp;&lt;tag&gt;") == "&nbsp;&lt;tag&gt;"


def test_leaves_clean_text_untouched():
    assert decode_numeric_entities("亘以") == "亘以"
    assert decode_numeric_entities("") == ""


@pytest.mark.parametrize(
    "bad",
    [
        "&#XD800;x",  # surrogate — not a valid scalar value
        "&#X110000;x",  # beyond U+10FFFF
        "&#X0;x",  # NUL: Postgres text cannot store it
        "&#X1F;x",  # C0 control
    ],
)
def test_refuses_unsafe_codepoints(bad):
    """Leave the row untouched rather than write something unstorable.

    A backfill that half-decodes a row is worse than one that skips it: the
    skipped rows stay findable by the same LIKE '%&#%' query.
    """
    assert decode_numeric_entities(bad) == bad


def test_partial_decode_is_all_or_nothing_per_reference():
    """One unsafe reference must not block the safe ones in the same string."""
    out = decode_numeric_entities("&#X4E98;&#XD800;")
    assert out == "亘&#XD800;"


def test_is_idempotent():
    once = decode_numeric_entities("&#X4E98;以")
    assert decode_numeric_entities(once) == once


def test_importer_strip_html_no_longer_manufactures_the_bad_string():
    """Regression guard on the importer that created the mess.

    buddhaspace.org double-escapes rare characters, so the source carries
    ``&amp;#X4E98;``. The old hand-rolled decoder replaced ``&amp;`` with ``&``
    first and had no numeric-reference pass, so it produced the literal
    ``&#X4E98;`` and stored that. Re-running the importer must now yield the
    character itself.
    """
    from scripts.archive.imports.import_buddhaspace import _strip_html

    assert _strip_html("<p>&amp;#X4E98;以</p>") == "亘以"
    # Single-escaped input must work too.
    assert _strip_html("<p>&#X4E98;以</p>") == "亘以"
    # Ordinary named entities still decode.
    assert _strip_html("<p>A &amp; B</p>") == "A & B"


# ---------------------------------------------------------------------------
# 命名实体（2026-08-25）：佛光大辞典「般若」条释义显示 ``praj&ntilde;ā``。这批词条
# 来自 mdict 导入器，它只手工替换了 amp/quot/#39/nbsp/lt/gt 六个，其余命名实体原样
# 落库。decode_entities() 是给回填脚本用的总入口：数字 → 命名 → 再数字（双重转义
# ``&amp;#X4E98;`` 要两轮），只认带分号的、HTML5 认识的名字。
# ---------------------------------------------------------------------------


def test_decodes_named_entity_seen_in_prod():
    assert decode_entities("praj&ntilde;ā") == "prajñā"
    assert decode_entities("Prajñāpāramitā &mdash; 般若") == "Prajñāpāramitā — 般若"


def test_named_pass_also_handles_markup_entities():
    # 释义正文里存的 ``&lt;`` 在页面上就显示成 ``&lt;``（前端按纯文本渲染），一样是错的。
    # 生产实数（2026-08-25）：10,596 行受影响，&amp; 12,109 处、&rarr; 1,749、&ntilde; 1,068。
    assert decode_entities("A &amp; B") == "A & B"
    assert decode_entities("&lt;tag&gt; &quot;q&quot;") == '<tag> "q"'
    assert decode_entities("参见 &rarr; 般若") == "参见 → 般若"


def test_nbsp_becomes_a_plain_space_like_the_importers_do():
    assert decode_entities("a&nbsp;b") == "a b"
    assert "\xa0" not in decode_entities("a&nbsp;b")


def test_double_escaped_numeric_reference_needs_two_rounds():
    # buddhaspace 的老病：``&amp;#X4E98;`` —— 先解成 ``&#X4E98;`` 再解成字。
    assert decode_entities("&amp;#X4E98;以") == "亘以"


def test_bare_ampersand_and_unknown_names_are_left_alone():
    assert decode_entities("A & B") == "A & B"
    assert decode_entities("&foo;") == "&foo;"
    # 没有分号的不碰：``&ntilde`` 在 HTML 里也合法，但这里只修确定坏了的形态。
    assert decode_entities("&ntilde") == "&ntilde"
    assert decode_entities("") == ""


def test_named_pass_keeps_unsafe_numeric_refusal():
    assert decode_entities("&#XD800;x") == "&#XD800;x"


def test_decode_entities_is_idempotent():
    once = decode_entities("praj&ntilde;ā &amp;#X4E98;")
    assert decode_entities(once) == once == "prajñā 亘"


def test_select_sql_finds_named_entities_too():
    """回填 SELECT 只查 '&#' 会漏掉 ``&ntilde;`` 这类行 —— 修脚本却查不出行等于没修。"""
    assert "&[A-Za-z][A-Za-z0-9]{1,31};" in SELECT_SQL
    assert "LIKE '%&#%'" in SELECT_SQL
