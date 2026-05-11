from pathlib import Path

from clusters import (
    FNCluster,
    FNRecord,
    is_valid,
    load_all_clusters,
    validate_cluster,
)

CLUSTERS_DIR = Path(__file__).resolve().parents[1] / "eval_clusters"


def _r(txn_id: str, **overrides) -> FNRecord:
    txn = {
        "amount": "10.00",
        "merchant_id": f"m_{txn_id}",
        "card_id": f"c_{txn_id}",
        "device_id": f"d_{txn_id}",
    }
    txn.update(overrides)
    return FNRecord(txn_id=txn_id, txn=txn, ctx={}, analyst_note="")


def test_well_formed_cluster_passes():
    cluster = FNCluster(
        cluster_id="ok",
        fn_records=tuple(_r(f"t{i}") for i in range(6)),
    )
    assert is_valid(cluster)


def test_too_few_fns_is_rejected():
    cluster = FNCluster(cluster_id="few", fn_records=tuple(_r(f"t{i}") for i in range(3)))
    issues = validate_cluster(cluster)
    assert any("too few" in i for i in issues)


def test_single_card_is_rejected():
    cluster = FNCluster(
        cluster_id="onecard",
        fn_records=tuple(_r(f"t{i}", card_id="c_same") for i in range(6)),
    )
    issues = validate_cluster(cluster)
    assert any("card_id" in i for i in issues)


def test_single_merchant_is_rejected():
    cluster = FNCluster(
        cluster_id="onemerch",
        fn_records=tuple(_r(f"t{i}", merchant_id="m_same") for i in range(6)),
    )
    issues = validate_cluster(cluster)
    assert any("merchant_id" in i for i in issues)


def test_seed_clusters_load_and_classify_correctly():
    clusters = load_all_clusters(CLUSTERS_DIR)
    by_id = {c.cluster_id: c for c in clusters}
    assert "valid_promo_code_abuse_v1" in by_id
    assert "adversarial_too_few" in by_id
    assert "adversarial_single_customer" in by_id

    for cid, cluster in by_id.items():
        if cid.startswith("valid_"):
            assert is_valid(cluster), f"{cid} should validate but got {validate_cluster(cluster)}"
        elif cid.startswith("adversarial_"):
            assert not is_valid(cluster), f"{cid} should fail validation"
