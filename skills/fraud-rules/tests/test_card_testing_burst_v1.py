from decimal import Decimal

from rules.card_testing_burst_v1 import applies, confidence, scheme_id
from schemas import EntityContext


def _ctx(**overrides) -> EntityContext:
    return EntityContext(**overrides)


def test_metadata(make_txn):
    assert scheme_id == "card_testing_burst_v1"
    assert 0 < confidence <= 1


# --- positives ---

def test_classic_burst_fires(make_txn):
    txn = make_txn(amount="0.50")
    ctx = _ctx(card_txn_count_60s=7, card_min_amount_60s=Decimal("0.50"))
    assert applies(txn, ctx) is True


def test_minimum_burst_fires(make_txn):
    # 4 prior + current = 5 in the 60s window
    txn = make_txn(amount="2.00")
    ctx = _ctx(card_txn_count_60s=4, card_min_amount_60s=Decimal("2.00"))
    assert applies(txn, ctx) is True


def test_burst_with_mixed_amounts_fires_on_low_min(make_txn):
    txn = make_txn(amount="100.00")
    ctx = _ctx(card_txn_count_60s=8, card_min_amount_60s=Decimal("0.99"))
    assert applies(txn, ctx) is True


# --- negatives ---

def test_below_count_threshold_does_not_fire(make_txn):
    txn = make_txn()
    ctx = _ctx(card_txn_count_60s=3, card_min_amount_60s=Decimal("0.50"))
    assert applies(txn, ctx) is False


def test_above_min_amount_does_not_fire(make_txn):
    txn = make_txn()
    ctx = _ctx(card_txn_count_60s=10, card_min_amount_60s=Decimal("7.50"))
    assert applies(txn, ctx) is False


def test_no_60s_history_does_not_fire(make_txn):
    txn = make_txn()
    ctx = _ctx(card_txn_count_60s=0, card_min_amount_60s=None)
    assert applies(txn, ctx) is False
