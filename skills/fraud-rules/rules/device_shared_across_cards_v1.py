"""Device fingerprint shared across many cards.

One device seen with 6+ distinct cards over its lifetime is a synthetic-identity ring
or a bust-out scheme — legitimate households rarely exceed 3-4 cards per device.
"""

from schemas import EntityContext, Transaction

scheme_id = "device_shared_across_cards_v1"
confidence = 0.8
created_at = "2026-05-11"
author = "human:gene"


def applies(txn: Transaction, ctx: EntityContext) -> bool:
    return ctx.device_distinct_cards_lifetime >= 5
