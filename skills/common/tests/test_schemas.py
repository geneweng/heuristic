from datetime import datetime, timedelta
from decimal import Decimal

from schemas import EntityContext, Transaction, build_context


def _txn(
    txn_id: str,
    minutes_ago: int = 0,
    *,
    seconds_ago: int = 0,
    card_id: str = "c1",
    device_id: str = "d1",
    merchant_id: str = "m1",
    amount: str = "10.00",
    approved: bool = True,
    country: str = "US",
    base: datetime = datetime(2026, 5, 11, 12, 0, 0),
) -> Transaction:
    return Transaction(
        txn_id=txn_id,
        ts=base - timedelta(minutes=minutes_ago, seconds=seconds_ago),
        amount=Decimal(amount),
        currency="USD",
        merchant_id=merchant_id,
        merchant_category="grocery",
        card_id=card_id,
        device_id=device_id,
        ip="1.2.3.4",
        country=country,
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
    assert ctx.card_txn_count_60s == 0
    assert ctx.card_min_amount_60s is None
    assert ctx.current_device_seen_before_for_card is False
    assert ctx.prev_country is None


def test_build_context_60s_window_and_min_amount():
    history = [
        _txn("a", seconds_ago=10, amount="2.00"),
        _txn("b", seconds_ago=30, amount="1.50"),
        _txn("c", seconds_ago=120, amount="100.00"),  # outside 60s
    ]
    current = _txn("d", seconds_ago=0)
    ctx = build_context(history, current)
    assert ctx.card_txn_count_60s == 2
    assert ctx.card_min_amount_60s == Decimal("1.50")


def test_build_context_flags_new_device_for_aged_card():
    history = [_txn("a", minutes_ago=60, device_id="d_old")]
    current = _txn("b", minutes_ago=0, device_id="d_new")
    ctx = build_context(history, current)
    assert ctx.current_device_seen_before_for_card is False


def test_build_context_flags_known_device():
    history = [_txn("a", minutes_ago=60, device_id="d1")]
    current = _txn("b", minutes_ago=0, device_id="d1")
    ctx = build_context(history, current)
    assert ctx.current_device_seen_before_for_card is True


def test_build_context_records_prev_country():
    history = [
        Transaction(
            txn_id="a",
            ts=datetime(2026, 5, 11, 11, 30, 0),
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
    ]
    current = _txn("b", minutes_ago=0)
    ctx = build_context(history, current)
    assert ctx.prev_country == "US"
