from rules.decline_then_approve_v1 import applies, scheme_id
from schemas import EntityContext


def test_metadata():
    assert scheme_id == "decline_then_approve_v1"


# --- positives ---

def test_two_declines_then_approve_fires(make_txn):
    txn = make_txn(approved=True)
    ctx = EntityContext(card_decline_count_1h=2)
    assert applies(txn, ctx) is True


def test_many_declines_then_approve_fires(make_txn):
    txn = make_txn(approved=True)
    ctx = EntityContext(card_decline_count_1h=8)
    assert applies(txn, ctx) is True


def test_three_declines_then_approve_fires(make_txn):
    txn = make_txn(approved=True, amount="42.00")
    ctx = EntityContext(card_decline_count_1h=3)
    assert applies(txn, ctx) is True


# --- negatives ---

def test_below_decline_threshold_does_not_fire(make_txn):
    txn = make_txn(approved=True)
    ctx = EntityContext(card_decline_count_1h=1)
    assert applies(txn, ctx) is False


def test_declines_but_current_also_declined_does_not_fire(make_txn):
    txn = make_txn(approved=False)
    ctx = EntityContext(card_decline_count_1h=5)
    assert applies(txn, ctx) is False


def test_no_declines_does_not_fire(make_txn):
    txn = make_txn(approved=True)
    ctx = EntityContext(card_decline_count_1h=0)
    assert applies(txn, ctx) is False
