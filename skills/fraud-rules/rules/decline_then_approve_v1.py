"""Decline-retry signature.

Fraudsters iterate on amount or merchant until an auth lands. Two+ declines in the
last hour followed by an approve on the same card is the classic retry pattern.
"""

from schemas import EntityContext, Transaction

scheme_id = "decline_then_approve_v1"
confidence = 0.75
created_at = "2026-05-11"
author = "human:gene"


def applies(txn: Transaction, ctx: EntityContext) -> bool:
    return ctx.card_decline_count_1h >= 2 and txn.approved
