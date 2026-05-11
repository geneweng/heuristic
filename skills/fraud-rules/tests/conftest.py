from datetime import datetime
from decimal import Decimal

import pytest

from schemas import Transaction


@pytest.fixture
def make_txn():
    def _make(
        txn_id: str = "t1",
        *,
        amount: str = "10.00",
        currency: str = "USD",
        country: str = "US",
        card_id: str = "c1",
        device_id: str = "d1",
        merchant_id: str = "m1",
        approved: bool = True,
        ts: datetime = datetime(2026, 5, 11, 12, 0, 0),
    ) -> Transaction:
        return Transaction(
            txn_id=txn_id,
            ts=ts,
            amount=Decimal(amount),
            currency=currency,
            merchant_id=merchant_id,
            merchant_category="grocery",
            card_id=card_id,
            device_id=device_id,
            ip="1.2.3.4",
            country=country,
            approved=approved,
        )

    return _make
