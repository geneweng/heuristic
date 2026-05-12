"""Feature engineering shared by training and per-txn scoring.

Single source of truth: anything `train.py` learns is what `score()` extracts
at inference time. If the training set sees `log_amount` here, the scorer
must produce `log_amount` the same way.
"""

from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal
from typing import Iterable

import numpy as np
import pandas as pd

from schemas import EntityContext, Transaction


COUNTRY_VOCAB = ["US", "DE", "FR", "GB", "JP", "CA", "AU", "BR", "MX", "NL"]
CATEGORY_VOCAB = [
    "grocery", "restaurant", "retail-apparel", "retail-electronics",
    "gas", "gaming", "online-cash-out", "subscription", "luxury",
    "travel", "prepaid-card", "gift-card",
]

# Numerical features in stable order — the trained model expects this exact
# layout. `FEATURE_NAMES` is what train.py writes alongside the model so the
# scorer can recover the original schema.
NUMERIC_FEATURES = [
    "log_amount",
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "approved",
    "card_age_days",
    "card_txn_count_24h",
    "card_amount_24h",
    "card_distinct_merchants_24h",
    "card_distinct_devices_lifetime",
    "card_seconds_since_last_txn",
    "card_decline_count_1h",
    "card_txn_count_60s",
    "device_distinct_cards_lifetime",
    "current_device_seen_before_for_card",
]

FEATURE_NAMES = (
    NUMERIC_FEATURES
    + [f"country_{c}" for c in COUNTRY_VOCAB]
    + [f"category_{c}" for c in CATEGORY_VOCAB]
)


def _onehot(value: str, vocab: list[str]) -> list[int]:
    return [1 if value == v else 0 for v in vocab]


def featurize_one(txn: Transaction, ctx: EntityContext) -> np.ndarray:
    """Per-txn feature vector. Used at inference time."""
    amt = float(txn.amount)
    row = [
        math.log1p(amt),
        txn.ts.hour,
        txn.ts.weekday(),
        1 if txn.ts.weekday() >= 5 else 0,
        1 if txn.approved else 0,
        ctx.card_age_days,
        ctx.card_txn_count_24h,
        float(ctx.card_amount_24h),
        ctx.card_distinct_merchants_24h,
        ctx.card_distinct_devices_lifetime,
        ctx.card_seconds_since_last_txn if ctx.card_seconds_since_last_txn is not None else 99_999,
        ctx.card_decline_count_1h,
        ctx.card_txn_count_60s,
        ctx.device_distinct_cards_lifetime,
        1 if ctx.current_device_seen_before_for_card else 0,
    ]
    row += _onehot(txn.country, COUNTRY_VOCAB)
    row += _onehot(txn.merchant_category, CATEGORY_VOCAB)
    return np.asarray(row, dtype=np.float32)


def featurize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Streaming featurizer. Sorts by ts, walks once, maintains per-card +
    per-device running state. Slower than full pandas vectorization but
    reuses `schemas.build_context()` so training features exactly match what
    the live scorer computes."""
    df = df.sort_values("ts").reset_index(drop=True).copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)

    per_card_history: dict[str, list[Transaction]] = {}
    per_device_cards: dict[str, set[str]] = {}
    rows: list[np.ndarray] = []

    from schemas import build_context  # local to keep import surface clean

    for r in df.itertuples(index=False):
        amount = r.amount if isinstance(r.amount, Decimal) else Decimal(str(r.amount))
        txn = Transaction(
            txn_id=r.txn_id,
            ts=r.ts.to_pydatetime(),
            amount=amount,
            currency=r.currency,
            merchant_id=r.merchant_id,
            merchant_category=r.merchant_category,
            card_id=r.card_id,
            device_id=r.device_id,
            ip=r.ip,
            country=r.country,
            approved=bool(r.approved),
            city=None,
            bin=str(r.bin) if r.bin else None,
        )
        history = per_card_history.get(txn.card_id, [])
        ctx = build_context(history, txn)
        # device_distinct_cards_lifetime: maintain explicitly since build_context
        # would need the entire stream's history of that device — too expensive.
        seen_cards = per_device_cards.setdefault(txn.device_id, set())
        seen_cards.add(txn.card_id)
        ctx = ctx.model_copy(update={"device_distinct_cards_lifetime": len(seen_cards)})

        rows.append(featurize_one(txn, ctx))
        per_card_history.setdefault(txn.card_id, []).append(txn)

    return pd.DataFrame(np.stack(rows), columns=FEATURE_NAMES, index=df.index)
