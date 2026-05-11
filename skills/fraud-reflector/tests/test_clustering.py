from clustering import cluster_fns
from clusters import FNRecord


def _fn(txn_id: str, **txn_overrides) -> FNRecord:
    txn = {
        "amount": "25.00",
        "merchant_id": f"m_{txn_id}",
        "card_id": f"c_{txn_id}",
        "device_id": f"d_{txn_id}",
        "country": "US",
        "merchant_category": "grocery",
    }
    txn.update(txn_overrides)
    return FNRecord(txn_id=txn_id, txn=txn, ctx={"card_age_days": 200})


def test_groups_by_shared_features():
    fns = [_fn(f"a{i}") for i in range(6)]
    clusters = cluster_fns(fns, min_size=5)
    assert len(clusters) == 1
    assert clusters[0].fn_records[0].txn_id == "a0"


def test_below_min_size_is_dropped():
    fns = [_fn(f"b{i}") for i in range(4)]
    assert cluster_fns(fns, min_size=5) == []


def test_distinct_buckets_separate():
    # Two distinct merchant_category groups, each of size 5.
    fns = [_fn(f"g{i}", merchant_category="grocery") for i in range(5)] + [
        _fn(f"e{i}", merchant_category="electronics") for i in range(5)
    ]
    clusters = cluster_fns(fns, min_size=5)
    assert len(clusters) == 2
    categories = {c.cluster_id.split("_")[2] for c in clusters}
    assert categories == {"grocery", "electronics"}


def test_cluster_summary_describes_bucket():
    fns = [_fn(f"x{i}", country="DE") for i in range(5)]
    [cluster] = cluster_fns(fns, min_size=5)
    assert "country=DE" in cluster.analyst_summary
    assert "merchant_category=grocery" in cluster.analyst_summary
