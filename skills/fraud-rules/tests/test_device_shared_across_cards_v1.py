from rules.device_shared_across_cards_v1 import applies, scheme_id
from schemas import EntityContext


def test_metadata():
    assert scheme_id == "device_shared_across_cards_v1"


# --- positives ---

def test_six_cards_on_device_fires(make_txn):
    txn = make_txn()
    ctx = EntityContext(device_distinct_cards_lifetime=6)
    assert applies(txn, ctx) is True


def test_many_cards_on_device_fires(make_txn):
    txn = make_txn()
    ctx = EntityContext(device_distinct_cards_lifetime=20)
    assert applies(txn, ctx) is True


def test_ring_size_seven_fires(make_txn):
    txn = make_txn()
    ctx = EntityContext(device_distinct_cards_lifetime=7)
    assert applies(txn, ctx) is True


# --- negatives ---

def test_at_threshold_does_not_fire(make_txn):
    txn = make_txn()
    ctx = EntityContext(device_distinct_cards_lifetime=5)
    assert applies(txn, ctx) is False


def test_typical_household_does_not_fire(make_txn):
    txn = make_txn()
    ctx = EntityContext(device_distinct_cards_lifetime=3)
    assert applies(txn, ctx) is False


def test_single_card_does_not_fire(make_txn):
    txn = make_txn()
    ctx = EntityContext(device_distinct_cards_lifetime=1)
    assert applies(txn, ctx) is False
