"""One definition of the MITRA quality gate, shared across read paths.

``mitra_alignments`` rows carry a proxy quality score (``mitra_e_score``, a
BGE-M3 cosine; the real MITRA-E semantic gate is a later phase). Rows below
``settings.mitra_min_score`` are low-quality alignments that should not be
served. The predicate is **NULL-PERMISSIVE**: rows whose score has not been
backfilled yet still pass, so enabling the gate before the backfill completes is
a no-op and it self-activates as scores land.

The RAG context path (``rag_retrieval._attach_mitra_parallels``) already applies
this gate inline (with its own score-ordered window over the
``ix_mitra_align_chunk_escore`` partial index). This module mirrors that exact
predicate so the two paths that historically **bypassed** the gate — the
citation drawer (``alignment_read_model.get_chunk_parallels``) and the coverage
catalog (``api.alignment.compute_alignment_catalog``) — can adopt it without
drifting on what "gated" means. Same flag/threshold, same ``:min_score`` bind.
"""

from app.config import settings


def build_mitra_score_predicate(
    enabled: bool, threshold: float, column: str = "mitra_e_score"
) -> tuple[str, dict]:
    """Pure core: the gate predicate + bind params, or ``("", {})`` when off.

    ``column`` lets callers qualify the name for aliased queries
    (e.g. ``"ma.mitra_e_score"``). The predicate is NULL-permissive.
    """
    if not enabled:
        return "", {}
    return (
        f"({column} IS NULL OR {column} >= :min_score)",
        {"min_score": threshold},
    )


def mitra_score_predicate(column: str = "mitra_e_score") -> tuple[str, dict]:
    """Config-driven wrapper: reads the live gate flag + threshold from settings."""
    return build_mitra_score_predicate(
        settings.enable_mitra_score_gate, settings.mitra_min_score, column
    )
