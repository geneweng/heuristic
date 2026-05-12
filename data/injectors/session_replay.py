"""Scheme B — session-replay signature.

An attacker has captured a legitimate user's session token and is replaying
checkouts from an automated harness. All txns share identical IP + user-agent
fingerprint (we use a fixed device_id as a proxy), inter-arrival jitter is
small (consistent 17-second spacing), merchant_category is 'gaming' (high-
fraud, instant fulfillment). Amount varies within a tight range — randomized
by the attacker to look organic, but the regularity is the tell.

The frozen ML doesn't see "inter-arrival regularity" as a feature. Synthetic.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from ._common import label_record, run_record

SCHEME_ID = "session_replay_v1"
FIXED_DEVICE = "d_replay_harness_42"
FIXED_IP = "203.0.113.99"


def generate(
    start_ts: datetime,
    *,
    count: int = 7,
    interval_seconds: int = 17,
) -> list[tuple[dict, dict]]:
    out: list[tuple[dict, dict]] = []
    for i in range(count):
        ts = start_ts + timedelta(seconds=interval_seconds * i)
        txn_id = f"inj_sr_{i:03d}"
        amount = Decimal("47.50") + Decimal(i) * Decimal("0.25")
        rr = run_record(
            txn_id,
            ts=ts,
            amount=str(amount),
            card_id=f"c_sr_{i}",
            device_id=FIXED_DEVICE,
            ip=FIXED_IP,
            merchant_id=f"m_gaming_{i % 4}",
            merchant_category="gaming",
            country="US",
            ctx={
                "card_age_days": 60,
                "current_device_seen_before_for_card": False,
                "device_distinct_cards_lifetime": i + 1,
            },
        )
        lr = label_record(
            txn_id,
            scheme_id=SCHEME_ID,
            note="Identical device fingerprint + 17s jitter — replay harness",
            ts=ts,
        )
        out.append((rr, lr))
    return out
