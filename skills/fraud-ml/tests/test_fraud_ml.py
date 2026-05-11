from datetime import datetime
from decimal import Decimal

from fraud_ml import score
from schemas import EntityContext, Transaction


def _txn() -> Transaction:
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


def test_stub_returns_zero():
    out = score(_txn(), EntityContext())
    assert out["prob"] == 0.0
    assert out["top_features"] == []
