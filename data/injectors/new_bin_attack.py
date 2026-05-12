"""Scheme A — new BIN range attack.

A BIN (first 6 digits) issued by a newly-onboarded card-issuer is being abused
en masse. Each txn carries the same BIN, country routes through a corridor
(AT — Austria, picked for distinctness in the fixture), merchant_category is
'online-cash-out' (gift-card → crypto laundering category). Amounts cluster at
$199 — below typical issuer step-up thresholds.

The frozen ML never saw this BIN at training time, so it scores benign.
Synthetic — for #13 fixture only.
"""

from datetime import datetime, timedelta
from typing import Iterable

from ._common import label_record, run_record

SCHEME_ID = "new_bin_attack_v1"
TARGET_BIN = "654321"


def generate(
    start_ts: datetime,
    *,
    count: int = 7,
    interval_minutes: int = 8,
) -> list[tuple[dict, dict]]:
    out: list[tuple[dict, dict]] = []
    for i in range(count):
        ts = start_ts + timedelta(minutes=interval_minutes * i)
        txn_id = f"inj_nba_{i:03d}"
        rr = run_record(
            txn_id,
            ts=ts,
            amount="199.00",
            card_id=f"c_nba_{i}",
            device_id=f"d_nba_{i}",
            merchant_id=f"m_oco_{i % 3}",       # 3 distinct cash-out merchants
            merchant_category="online-cash-out",
            country="AT",
            bin=TARGET_BIN,
            ctx={
                "card_age_days": 14,
                "current_device_seen_before_for_card": False,
                "card_distinct_devices_lifetime": 1,
                "device_distinct_cards_lifetime": 1,
            },
        )
        lr = label_record(
            txn_id,
            scheme_id=SCHEME_ID,
            note=f"BIN {TARGET_BIN} online-cash-out in AT — fresh issuer abuse",
            ts=ts,
        )
        out.append((rr, lr))
    return out
