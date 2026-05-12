from datetime import datetime, timezone

import pytest

from data.injectors import INJECTORS, new_bin_attack, session_replay, synthetic_id_ring


@pytest.fixture
def t0() -> datetime:
    return datetime(2026, 5, 4, 9, 0, 0, tzinfo=timezone.utc)


def test_registry_exposes_three_named_schemes():
    assert set(INJECTORS) == {"new_bin_attack", "session_replay", "synthetic_id_ring"}


def test_each_record_has_paired_label(t0):
    for name, fn in INJECTORS.items():
        pairs = fn(t0)
        assert pairs, f"{name} returned no records"
        for rr, lr in pairs:
            assert rr["txn"]["txn_id"] == lr["txn_id"]
            assert lr["label"] == "fraud"
            assert lr["scheme_id"]


def test_new_bin_attack_signature(t0):
    pairs = new_bin_attack(t0)
    assert len(pairs) == 7
    bins = {rr["txn"]["bin"] for rr, _ in pairs}
    countries = {rr["txn"]["country"] for rr, _ in pairs}
    cats = {rr["txn"]["merchant_category"] for rr, _ in pairs}
    assert bins == {"654321"}
    assert countries == {"AT"}
    assert cats == {"online-cash-out"}


def test_session_replay_uses_one_device_and_close_spacing(t0):
    pairs = session_replay(t0)
    devices = {rr["txn"]["device_id"] for rr, _ in pairs}
    assert len(devices) == 1
    times = sorted(rr["ts"] for rr, _ in pairs)
    # 17-second spacing means 7 records span ~108 seconds
    span = (
        datetime.fromisoformat(times[-1]) - datetime.fromisoformat(times[0])
    ).total_seconds()
    assert span < 180


def test_synthetic_id_ring_has_three_devices_three_cards_each(t0):
    pairs = synthetic_id_ring(t0)
    assert len(pairs) == 9
    from collections import Counter
    by_device = Counter(rr["txn"]["device_id"] for rr, _ in pairs)
    assert len(by_device) == 3
    assert all(c == 3 for c in by_device.values())


def test_all_injected_records_have_fraud_label(t0):
    for fn in INJECTORS.values():
        for _, lr in fn(t0):
            assert lr["label"] == "fraud"


def test_labels_arrive_12h_after_txn(t0):
    for fn in INJECTORS.values():
        for rr, lr in fn(t0):
            txn_ts = datetime.fromisoformat(rr["ts"])
            label_ts = datetime.fromisoformat(lr["labeled_at"])
            assert 0 < (label_ts - txn_ts).total_seconds() <= 12 * 3600 + 60
