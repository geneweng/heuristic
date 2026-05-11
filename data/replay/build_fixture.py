"""Generate the seed replay fixture used by `make replay`.

Deterministic — re-running produces identical output. Aim is one clear positive per
seed rule plus a handful of benign negatives. Replace with the IEEE-CIS replay split
once #2 lands.

Run: `python data/replay/build_fixture.py`
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

OUT = Path(__file__).parent / "fixture.jsonl"
BASE = datetime(2026, 5, 1, 12, 0, 0)


def _rec(
    txn_id: str,
    *,
    delta_minutes: float = 0,
    delta_seconds: float = 0,
    delta_days: float = 0,
    amount: str = "10.00",
    currency: str = "USD",
    card_id: str = "c_default",
    device_id: str = "d_default",
    merchant_id: str = "m_default",
    country: str = "US",
    approved: bool = True,
    true_scheme_id: str | None = None,
    is_fraud: bool = False,
) -> dict:
    ts = BASE + timedelta(days=delta_days, minutes=delta_minutes, seconds=delta_seconds)
    return {
        "txn_id": txn_id,
        "ts": ts.isoformat(),
        "amount": str(Decimal(amount)),
        "currency": currency,
        "merchant_id": merchant_id,
        "merchant_category": "grocery",
        "card_id": card_id,
        "device_id": device_id,
        "ip": "1.2.3.4",
        "country": country,
        "approved": approved,
        "true_scheme_id": true_scheme_id,
        "is_fraud": is_fraud,
    }


def card_testing_burst() -> list[dict]:
    # 6 small auths on the same card in 60s. Rule fires from the 5th onward
    # (4 prior + current = 5 in window).
    card = "c_cb1"
    device = "d_cb1"
    recs = []
    for i, sec in enumerate([0, 8, 16, 24, 32, 40]):
        is_pos = i >= 4
        recs.append(
            _rec(
                f"cb{i}",
                delta_seconds=sec,
                amount="1.50",
                card_id=card,
                device_id=device,
                merchant_id=f"m_cb_{i}",
                true_scheme_id="card_testing_burst_v1" if is_pos else None,
                is_fraud=is_pos,
            )
        )
    return recs


def geo_country_jump() -> list[dict]:
    # Two events. Prior US auth, then a non-US auth within 30 min.
    return [
        _rec("gj1a", delta_minutes=60, card_id="c_gj1", device_id="d_gj1", country="US"),
        _rec(
            "gj1b",
            delta_minutes=70,
            card_id="c_gj1",
            device_id="d_gj1",
            country="DE",
            true_scheme_id="geo_country_jump_v1",
            is_fraud=True,
        ),
        _rec("gj2a", delta_minutes=200, card_id="c_gj2", device_id="d_gj2", country="JP"),
        _rec(
            "gj2b",
            delta_minutes=205,
            card_id="c_gj2",
            device_id="d_gj2",
            country="BR",
            true_scheme_id="geo_country_jump_v1",
            is_fraud=True,
        ),
    ]


def decline_then_approve() -> list[dict]:
    # 2 declines in the last hour, then an approve. Tag the approve.
    return [
        _rec("da1a", delta_minutes=400, card_id="c_da1", device_id="d_da1", approved=False),
        _rec("da1b", delta_minutes=410, card_id="c_da1", device_id="d_da1", approved=False),
        _rec(
            "da1c",
            delta_minutes=420,
            card_id="c_da1",
            device_id="d_da1",
            approved=True,
            true_scheme_id="decline_then_approve_v1",
            is_fraud=True,
        ),
    ]


def new_device_aged_card_high_value() -> list[dict]:
    # Aged history on one device, then a high-value txn on a brand-new device.
    return [
        _rec("nd1_hist", delta_days=-120, card_id="c_nd1", device_id="d_nd1_old"),
        _rec("nd1_hist2", delta_days=-30, card_id="c_nd1", device_id="d_nd1_old"),
        _rec(
            "nd1_trigger",
            delta_minutes=500,
            card_id="c_nd1",
            device_id="d_nd1_new",
            amount="850.00",
            true_scheme_id="new_device_aged_card_high_value_v1",
            is_fraud=True,
        ),
    ]


def device_shared_across_cards() -> list[dict]:
    # One device used by 6 distinct cards.
    device = "d_ring"
    recs = []
    for i in range(6):
        is_last = i == 5
        recs.append(
            _rec(
                f"ds{i}",
                delta_minutes=600 + i,
                card_id=f"c_ds_{i}",
                device_id=device,
                true_scheme_id="device_shared_across_cards_v1" if is_last else None,
                is_fraud=is_last,
            )
        )
    return recs


def benign() -> list[dict]:
    # Plain legit traffic — each (card, device) pair unique so it doesn't pollute the
    # device-ring or shared-context rules with cross-record correlations.
    return [
        _rec(
            f"b{i}",
            delta_minutes=1000 + i * 7,
            card_id=f"c_b_{i}",
            device_id=f"d_b_{i}",
            amount=f"{20 + i * 3}.00",
        )
        for i in range(12)
    ]


def build() -> list[dict]:
    recs = []
    recs.extend(card_testing_burst())
    recs.extend(geo_country_jump())
    recs.extend(decline_then_approve())
    recs.extend(new_device_aged_card_high_value())
    recs.extend(device_shared_across_cards())
    recs.extend(benign())
    return recs


def main() -> None:
    recs = build()
    OUT.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    pos = sum(1 for r in recs if r["is_fraud"])
    print(f"wrote {len(recs)} records ({pos} fraud) to {OUT}")


if __name__ == "__main__":
    main()
