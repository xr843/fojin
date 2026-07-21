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

from scripts.fix_dict_html_entities import decode_numeric_entities


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
