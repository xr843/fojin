"""Apparatus read-path tests.

No live Postgres in CI — following test_works_api.py, the AsyncSession is an
AsyncMock whose execute() returns a controlled result, so the real service
query/transform logic is exercised without a DB.
"""

from unittest.mock import AsyncMock, MagicMock

from app.services.content import get_juan_apparatus


def _reading(**kw):
    r = MagicMock()
    r.reading = kw.get("reading", "辯")
    r.witnesses = kw.get("witnesses", ["【宋】", "【元】"])
    r.resp = kw.get("resp", "Taisho")
    r.is_omission = kw.get("is_omission", False)
    return r


def _entry(**kw):
    e = MagicMock()
    e.char_start = kw.get("char_start", 4)
    e.char_end = kw.get("char_end", 5)
    e.lemma = kw.get("lemma", "辨")
    e.lemma_siglum = kw.get("lemma_siglum", "【大】")
    e.readings = kw.get("readings", [_reading()])
    return e


def _session_returning(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session = AsyncMock()
    session.execute.return_value = result
    return session


async def test_get_juan_apparatus_maps_entries_and_readings():
    session = _session_returning([_entry()])
    out = await get_juan_apparatus(session, text_id=1, juan_num=1)
    assert len(out) == 1
    e = out[0]
    assert (e["char_start"], e["char_end"]) == (4, 5)
    assert e["lemma"] == "辨"
    assert e["lemma_siglum"] == "【大】"
    assert e["readings"] == [
        {"reading": "辯", "witnesses": ["【宋】", "【元】"], "resp": "Taisho", "is_omission": False}
    ]


async def test_get_juan_apparatus_empty_when_none():
    session = _session_returning([])
    out = await get_juan_apparatus(session, text_id=1, juan_num=9)
    assert out == []
