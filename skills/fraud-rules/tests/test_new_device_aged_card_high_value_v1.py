from rules.new_device_aged_card_high_value_v1 import applies, scheme_id
from schemas import EntityContext


def test_metadata():
    assert scheme_id == "new_device_aged_card_high_value_v1"


# --- positives ---

def test_aged_card_new_device_high_amount_fires(make_txn):
    txn = make_txn(amount="800.00")
    ctx = EntityContext(card_age_days=120, current_device_seen_before_for_card=False)
    assert applies(txn, ctx) is True


def test_very_old_card_huge_amount_fires(make_txn):
    txn = make_txn(amount="2500.00")
    ctx = EntityContext(card_age_days=400, current_device_seen_before_for_card=False)
    assert applies(txn, ctx) is True


def test_just_over_amount_threshold_fires(make_txn):
    txn = make_txn(amount="500.01")
    ctx = EntityContext(card_age_days=91, current_device_seen_before_for_card=False)
    assert applies(txn, ctx) is True


# --- negatives ---

def test_known_device_does_not_fire(make_txn):
    txn = make_txn(amount="800.00")
    ctx = EntityContext(card_age_days=120, current_device_seen_before_for_card=True)
    assert applies(txn, ctx) is False


def test_young_card_does_not_fire(make_txn):
    txn = make_txn(amount="800.00")
    ctx = EntityContext(card_age_days=30, current_device_seen_before_for_card=False)
    assert applies(txn, ctx) is False


def test_low_amount_does_not_fire(make_txn):
    txn = make_txn(amount="50.00")
    ctx = EntityContext(card_age_days=120, current_device_seen_before_for_card=False)
    assert applies(txn, ctx) is False
