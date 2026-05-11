"""Card-testing burst.

Attackers verifying stolen PANs run many tiny auths in a few seconds — if any one
succeeds, the card is "live" and they sell or escalate. We flag when a single card
sees 5+ auths in 60 seconds with at least one under $5.
"""

from decimal import Decimal

from schemas import EntityContext, Transaction

scheme_id = "card_testing_burst_v1"
confidence = 0.95
created_at = "2026-05-11"
author = "human:gene"


def applies(txn: Transaction, ctx: EntityContext) -> bool:
    return (
        ctx.card_txn_count_60s >= 4
        and ctx.card_min_amount_60s is not None
        and ctx.card_min_amount_60s < Decimal("5.00")
    )
