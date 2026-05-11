from datetime import datetime
from decimal import Decimal

from registry import _discover, evaluate
from schemas import EntityContext, Transaction


def _benign_txn() -> Transaction:
    return Transaction(
        txn_id="t1",
        ts=datetime(2026, 5, 11, 12, 0, 0),
        amount=Decimal("10.00"),
        currency="USD",
        merchant_id="m1",
        merchant_category="grocery",
        card_id="c1",
        device_id="d1",
        ip="1.2.3.4",
        country="US",
        approved=True,
    )


def test_registry_discovers_seed_rules():
    rules = _discover()
    scheme_ids = {r.scheme_id for r in rules}
    assert {
        "card_testing_burst_v1",
        "geo_country_jump_v1",
        "decline_then_approve_v1",
        "new_device_aged_card_high_value_v1",
        "device_shared_across_cards_v1",
    } <= scheme_ids


def test_benign_txn_with_neutral_context_fires_nothing():
    assert evaluate(_benign_txn(), EntityContext()) == []


def test_card_testing_pattern_fires_the_right_rule():
    txn = _benign_txn()
    ctx = EntityContext(card_txn_count_60s=6, card_min_amount_60s=Decimal("0.50"))
    fired = evaluate(txn, ctx)
    assert ("card_testing_burst_v1", 0.95) in fired
