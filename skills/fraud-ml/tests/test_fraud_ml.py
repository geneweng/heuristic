from datetime import datetime
from decimal import Decimal

from fraud_ml import score
from schemas import EntityContext, Transaction


def _txn(**overrides) -> Transaction:
    base = dict(
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
    base.update(overrides)
    return Transaction(**base)


def test_score_returns_prob_and_top_features():
    out = score(_txn(), EntityContext())
    assert 0.0 <= out["prob"] <= 1.0
    assert isinstance(out["top_features"], list)


def test_score_reacts_to_input():
    """Different contexts must produce different scores (otherwise the model
    isn't wired through)."""
    benign = score(_txn(amount=Decimal("12.00")), EntityContext(card_age_days=400))
    suspicious = score(
        _txn(amount=Decimal("1500.00"), country="DE", merchant_category="online-cash-out"),
        EntityContext(card_age_days=1, current_device_seen_before_for_card=False),
    )
    assert benign["prob"] != suspicious["prob"]


def test_top_features_drawn_from_feature_vocabulary():
    from features import FEATURE_NAMES

    out = score(_txn(), EntityContext())
    for name in out["top_features"]:
        assert name in FEATURE_NAMES
