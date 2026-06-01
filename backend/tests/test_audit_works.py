from scripts.audit_works import classify_origin, cluster_bucket


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
