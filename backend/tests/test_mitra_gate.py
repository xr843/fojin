"""The shared MITRA quality-gate predicate (mirrors the RAG gate, reused by the
drawer + catalog paths that historically bypassed it)."""

from app.services.mitra_gate import build_mitra_score_predicate


def test_disabled_gate_emits_no_predicate_and_no_binds():
    assert build_mitra_score_predicate(False, 0.30) == ("", {})


def test_enabled_gate_is_null_permissive_and_binds_min_score():
    pred, params = build_mitra_score_predicate(True, 0.30)
    # NULL-permissive: unscored (pre-backfill) rows must still pass, so enabling
    # the gate before the backfill runs is a no-op.
    assert "mitra_e_score IS NULL OR" in pred
    assert "mitra_e_score >= :min_score" in pred
    assert params == {"min_score": 0.30}


def test_column_can_be_qualified_for_aliased_queries():
    # RAG's CTE aliases the table as ``ma``; the drawer/catalog use the bare name.
    pred, _ = build_mitra_score_predicate(True, 0.5, column="ma.mitra_e_score")
    assert pred == "(ma.mitra_e_score IS NULL OR ma.mitra_e_score >= :min_score)"
