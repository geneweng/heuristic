from datetime import datetime
from decimal import Decimal

from registry import evaluate
from schemas import EntityContext, Transaction


def test_empty_registry_returns_no_fires():
    txn = Transaction(
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
    assert evaluate(txn, EntityContext()) == []
