"""Impossible geo-velocity across countries.

A card cannot physically be in two countries 30 minutes apart. When the previous auth
was in a different country and < 30 min has elapsed, this is remote-use (often a
compromised wallet or a card-not-present test from a botnet).
"""

from schemas import EntityContext, Transaction

scheme_id = "geo_country_jump_v1"
confidence = 0.85
created_at = "2026-05-11"
author = "human:gene"


def applies(txn: Transaction, ctx: EntityContext) -> bool:
    return (
        ctx.prev_country is not None
        and ctx.prev_country != txn.country
        and ctx.card_seconds_since_last_txn is not None
        and ctx.card_seconds_since_last_txn < 1800
    )
