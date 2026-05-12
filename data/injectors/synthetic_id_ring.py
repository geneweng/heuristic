"""Scheme C — synthetic-identity ring.

A bust-out ring: 3 fingerprinted devices, each used by 3 different fresh cards.
Individually no card looks worse than "new aged card making a luxury purchase
on a new device" — which is below the threshold the seed `new_device_aged_
card_high_value_v1` rule needs. The collective pattern only emerges when you
notice that the 9 cards form a ring across 3 shared devices, all in NL,
all luxury category, all $400–$600.

The frozen ML can't see the ring; rules don't yet. Synthetic.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from ._common import label_record, run_record

SCHEME_ID = "synthetic_id_ring_v1"


def generate(
    start_ts: datetime,
    *,
    count: int = 9,                # 3 devices × 3 cards
    interval_minutes: int = 5,
) -> list[tuple[dict, dict]]:
    if count > 9:
        count = 9  # ring topology is fixed at 9 for the demo
    devices = ["d_ring_a", "d_ring_b", "d_ring_c"]
    out: list[tuple[dict, dict]] = []
    for i in range(count):
        ts = start_ts + timedelta(minutes=interval_minutes * i)
        device = devices[i // 3]
        amount = Decimal("400") + Decimal(i) * Decimal("25")
        txn_id = f"inj_sir_{i:03d}"
        rr = run_record(
            txn_id,
            ts=ts,
            amount=str(amount),
            card_id=f"c_sir_{i}",
            device_id=device,
            merchant_id=f"m_lux_{i % 3}",
            merchant_category="luxury",
            country="NL",
            ctx={
                "card_age_days": 40,
                "current_device_seen_before_for_card": False,
                "device_distinct_cards_lifetime": (i % 3) + 1,
            },
        )
        lr = label_record(
            txn_id,
            scheme_id=SCHEME_ID,
            note=f"Ring topology: shared device {device}, NL luxury",
            ts=ts,
        )
        out.append((rr, lr))
    return out
