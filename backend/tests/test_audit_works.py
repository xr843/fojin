from scripts.audit_works import WorkRow, classify_origin, cluster_bucket, compute_metrics, select_audit_targets


def test_classify_origin_priority():
    # skt_title wins even when other schemes co-occur
    assert classify_origin({"skt_title", "sc_uid"}) == "pass1_skt"
    assert classify_origin({"sc_uid"}) == "pass2_sc"
    assert classify_origin({"toh"}) == "pass3_toh"
    assert classify_origin({"sc_uid", "toh"}) == "pass2_sc"
    assert classify_origin(set()) == "pass4_singleton"
    assert classify_origin({"taisho"}) == "pass4_singleton"  # unknown scheme → singleton


def test_cluster_bucket_boundaries():
    assert cluster_bucket(1) == "1"
    assert cluster_bucket(2) == "2"
    assert cluster_bucket(5) == "3-5"
    assert cluster_bucket(6) == "6-10"
    assert cluster_bucket(15) == "11-15"
    assert cluster_bucket(16) == ">15"


def _row(work_id, origin, canons, confidences):
    return WorkRow(
        work_id=work_id,
        slug=f"w{work_id}",
        title=f"title-{work_id}",
        origin_pass=origin,
        witness_count=len(confidences),
        canons=tuple(canons),
        confidences=tuple(confidences),
    )


def test_compute_metrics_core_ratios():
    rows = [
        _row(1, "pass1_skt", ["taisho", "kangyur"], ["auto", "auto"]),   # multi + cross-canon
        _row(2, "pass1_skt", ["taisho"], ["auto"]),                       # singleton
        _row(3, "pass2_sc", ["pali"], ["verified"]),                      # singleton, verified
        _row(4, "pass4_singleton", ["taisho"], ["auto"]),                 # singleton
    ]
    m = compute_metrics(rows)
    assert m["total_works"] == 4
    assert m["total_witnesses"] == 5
    assert m["multi_witness_works"] == 1
    assert m["singleton_works"] == 3
    assert m["cross_canon_works"] == 1
    assert m["by_origin"]["pass1_skt"]["works"] == 2
    assert m["by_origin"]["pass1_skt"]["witnesses"] == 3
    assert m["confidence_distribution"]["verified"] == 1
    assert m["confidence_distribution"]["auto"] == 4
    assert m["pass1_cluster_histogram"]["2"] == 1
    assert m["pass1_cluster_histogram"]["1"] == 1


def test_cross_canon_excludes_unknown_canon():
    rows = [
        _row(1, "pass1_skt", ["taisho", "?"], ["auto", "auto"]),       # NOT cross-canon
        _row(2, "pass1_skt", ["taisho", "kangyur"], ["auto", "auto"]), # cross-canon
    ]
    m = compute_metrics(rows)
    assert m["cross_canon_works"] == 1


def test_select_audit_targets_is_deterministic_and_pass1_multi_only():
    rows = [_row(i, "pass1_skt", ["taisho", "kangyur"], ["auto"] * (i % 4 + 2)) for i in range(50)]
    rows += [_row(99, "pass2_sc", ["pali"], ["verified", "verified"])]  # must be excluded
    top, sample = select_audit_targets(rows, top_n=5, random_n=5, seed=20260601)
    assert all(r.origin_pass == "pass1_skt" for r in top + sample)
    assert [r.witness_count for r in top] == sorted([r.witness_count for r in top], reverse=True)
    # deterministic: same seed → same ids
    _top2, sample2 = select_audit_targets(rows, top_n=5, random_n=5, seed=20260601)
    assert [r.work_id for r in sample] == [r.work_id for r in sample2]
    # top and sample do not overlap
    assert not ({r.work_id for r in top} & {r.work_id for r in sample})
