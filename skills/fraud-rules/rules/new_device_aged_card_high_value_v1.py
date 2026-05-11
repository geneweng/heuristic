"""Aged card lights up on a new device for a high-value purchase.

A card seen for 90+ days suddenly auths on a device never linked to it, for >$500.
Strong takeover signal — legitimate cardholders rarely buy expensive items from a
brand-new device on the first try.
"""

from decimal import Decimal

from schemas import EntityContext, Transaction

scheme_id = "new_device_aged_card_high_value_v1"
confidence = 0.7
created_at = "2026-05-11"
author = "human:gene"


def applies(txn: Transaction, ctx: EntityContext) -> bool:
    return (
        ctx.card_age_days > 90
        and not ctx.current_device_seen_before_for_card
        and txn.amount > Decimal("500")
    )
