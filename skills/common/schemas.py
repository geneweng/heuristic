from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class Transaction(BaseModel):
    """One payment authorization request.

    Rules and the ML model read this directly — keep names stable and obvious.
    """

    txn_id: str = Field(description="Unique authorization id from the processor.")
    ts: datetime = Field(description="Authorization timestamp, UTC.")
    amount: Decimal = Field(description="Auth amount in the txn currency (not normalized).")
    currency: str = Field(description="ISO 4217 currency code, uppercase.")
    merchant_id: str = Field(description="Stable merchant identifier (acquirer namespace).")
    merchant_category: str = Field(description="MCC bucket: grocery, travel, gaming, ...")
    card_id: str = Field(description="Tokenized card identifier (PAN hash). Never the PAN.")
    device_id: str = Field(description="Device fingerprint hash provided by the SDK.")
    ip: str = Field(description="Client IP at auth time.")
    city: str | None = Field(default=None, description="Resolved city from IP/geo, if known.")
    country: str = Field(description="ISO 3166 country code, uppercase.")
    approved: bool = Field(description="Whether the issuer approved the auth.")
    bin: str | None = Field(default=None, description="First 6 digits of PAN; used for BIN rules.")


class EntityContext(BaseModel):
    """Rolling per-card / per-device aggregates available at scoring time.

    Computed by `build_context()` from a window of recent transactions. All fields default
    to neutral values so rules can be written defensively without None-guards.
    """

    card_txn_count_24h: int = Field(default=0, description="Card auth attempts in last 24h.")
    card_amount_24h: Decimal = Field(
        default=Decimal("0"), description="Sum of approved auth amounts in last 24h, card currency."
    )
    card_distinct_merchants_24h: int = Field(
        default=0, description="Distinct merchant_ids the card touched in 24h."
    )
    card_distinct_devices_lifetime: int = Field(
        default=0, description="Distinct device_ids ever seen for this card."
    )
    card_seconds_since_last_txn: int | None = Field(
        default=None, description="Gap to previous auth; None if first-seen."
    )
    card_decline_count_1h: int = Field(
        default=0, description="Declined auths in the last hour on this card."
    )
    card_age_days: int = Field(default=0, description="Days since first-seen for this card.")
    card_txn_count_60s: int = Field(
        default=0, description="Card auth attempts in the last 60 seconds (card-testing signal)."
    )
    card_min_amount_60s: Decimal | None = Field(
        default=None, description="Smallest auth amount in the last 60s on this card; None if no prior."
    )
    current_device_seen_before_for_card: bool = Field(
        default=False,
        description="True if the current txn's device_id appears in the card's prior history.",
    )
    prev_country: str | None = Field(
        default=None, description="Country of the previous auth on this card; None if first-seen."
    )
    device_distinct_cards_lifetime: int = Field(
        default=0, description="Distinct card_ids ever seen on this device."
    )


def build_context(history: list[Transaction], current: Transaction) -> EntityContext:
    """Compute `EntityContext` for `current` from a window of prior transactions.

    `history` excludes `current`. No DB calls, no I/O — rules and tests need this to be a
    pure function. Input order doesn't matter; sorted internally.
    """
    history = sorted(history, key=lambda t: t.ts)
    same_card = [t for t in history if t.card_id == current.card_id]
    same_device = [t for t in history if t.device_id == current.device_id]

    in_24h = [t for t in same_card if (current.ts - t.ts).total_seconds() <= 86400]
    in_60s = [t for t in same_card if (current.ts - t.ts).total_seconds() <= 60]
    in_1h_declined = [
        t
        for t in same_card
        if (current.ts - t.ts).total_seconds() <= 3600 and not t.approved
    ]

    prev = same_card[-1] if same_card else None
    age_days = (
        (current.ts - same_card[0].ts).days if same_card else 0
    )

    return EntityContext(
        card_txn_count_24h=len(in_24h),
        card_amount_24h=sum((t.amount for t in in_24h if t.approved), Decimal("0")),
        card_distinct_merchants_24h=len({t.merchant_id for t in in_24h}),
        card_distinct_devices_lifetime=len({t.device_id for t in same_card}),
        card_seconds_since_last_txn=int((current.ts - prev.ts).total_seconds()) if prev else None,
        card_decline_count_1h=len(in_1h_declined),
        card_age_days=age_days,
        card_txn_count_60s=len(in_60s),
        card_min_amount_60s=min((t.amount for t in in_60s), default=None),
        current_device_seen_before_for_card=any(t.device_id == current.device_id for t in same_card),
        prev_country=prev.country if prev else None,
        device_distinct_cards_lifetime=len({t.card_id for t in same_device}),
    )
