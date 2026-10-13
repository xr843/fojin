"""The DILA person-sync INSERT must expose exactly the parameters the caller binds.

It used ``:props::json`` / ``:ext::json``; SQLAlchemy's text() parsed those as
params ``prop`` and ``ex``, so every nightly run since 2026-04 died with
``syntax error at or near ":"`` (561 times in the log) and no new DILA person
was ever imported.
"""

import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from sync_dila_combined import _INSERT_PERSON_SQL


def test_insert_binds_exactly_the_supplied_parameters():
    assert set(text(_INSERT_PERSON_SQL)._bindparams) == {"nz", "ne", "desc", "props", "ext"}


def test_no_postgres_cast_shorthand_on_bind_params():
    assert "::json" not in _INSERT_PERSON_SQL
