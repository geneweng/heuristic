from datetime import datetime, timedelta
from decimal import Decimal

from schemas import EntityContext, Transaction, build_context


def _txn(
    txn_id: str,
    minutes_ago: int,
    *,
    card_id: str = "c1",
    device_id: str = "d1",
    merchant_id: str = "m1",
    amount: str = "10.00",
    approved: bool = True,
    base: datetime = datetime(2026, 5, 11, 12, 0, 0),
) -> Transaction:
    return Transaction(
        txn_id=txn_id,
        ts=base - timedelta(minutes=minutes_ago),
        amount=Decimal(amount),
        currency="USD",
        merchant_id=merchant_id,
        merchant_category="grocery",
        card_id=card_id,
        device_id=device_id,
        ip="1.2.3.4",
        country="US",
        approved=approved,
    )


def test_entity_context_defaults_are_neutral():
    ctx = EntityContext()
    assert ctx.card_txn_count_24h == 0
    assert ctx.card_amount_24h == Decimal("0")
    assert ctx.card_seconds_since_last_txn is None


def test_build_context_aggregates_24h_window():
    history = [
        _txn("a", minutes_ago=60, amount="5.00"),
        _txn("b", minutes_ago=30, amount="7.00", merchant_id="m2"),
        _txn("c", minutes_ago=2000, amount="100.00"),  # outside 24h
    ]
    current = _txn("d", minutes_ago=0, amount="3.00")
    ctx = build_context(history, current)

    assert ctx.card_txn_count_24h == 2
    assert ctx.card_amount_24h == Decimal("12.00")
    assert ctx.card_distinct_merchants_24h == 2
    assert ctx.card_seconds_since_last_txn == 30 * 60


def test_build_context_counts_recent_declines():
    history = [
        _txn("a", minutes_ago=10, approved=False),
        _txn("b", minutes_ago=20, approved=False),
        _txn("c", minutes_ago=120, approved=False),  # outside 1h
    ]
    current = _txn("d", minutes_ago=0)
    ctx = build_context(history, current)
    assert ctx.card_decline_count_1h == 2


def test_build_context_handles_first_seen_card():
    current = _txn("first", minutes_ago=0)
    ctx = build_context([], current)
    assert ctx.card_seconds_since_last_txn is None
    assert ctx.card_age_days == 0
    assert ctx.card_distinct_devices_lifetime == 0
