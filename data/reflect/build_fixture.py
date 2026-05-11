"""Generate a deterministic reflect fixture: runs + labels for `make reflect`.

Builds a runs/<date>.jsonl + labels/labels.jsonl pair containing a fraud
scheme the seed rules miss — a "new card / new device / high-value
electronics" pattern that none of the five seed rules catch by design. The
reflector should find these as FNs, cluster them, and (in live mode) propose
a new rule.

Run: `python data/reflect/build_fixture.py`
"""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "runs"
LABELS_PATH = REPO_ROOT / "labels" / "labels.jsonl"
BASE = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)


def _run_record(
    txn_id: str,
    *,
    delta_minutes: int,
    amount: str,
    card_id: str,
    device_id: str,
    merchant_category: str,
    country: str = "US",
    card_age_days: int = 200,
    device_seen_before: bool = True,
) -> dict:
    ts = BASE + timedelta(minutes=delta_minutes)
    return {
        "ts": ts.isoformat(),
        "txn": {
            "txn_id": txn_id,
            "ts": ts.isoformat(),
            "amount": amount,
            "currency": "USD",
            "merchant_id": f"m_{txn_id}",
            "merchant_category": merchant_category,
            "card_id": card_id,
            "device_id": device_id,
            "ip": "1.2.3.4",
            "country": country,
            "approved": True,
            "city": None,
            "bin": None,
        },
        "ctx": {
            "card_age_days": card_age_days,
            "current_device_seen_before_for_card": device_seen_before,
            "card_txn_count_24h": 0,
            "card_amount_24h": "0",
            "card_distinct_merchants_24h": 0,
            "card_distinct_devices_lifetime": 1,
            "card_seconds_since_last_txn": None,
            "card_decline_count_1h": 0,
            "card_txn_count_60s": 0,
            "card_min_amount_60s": None,
            "prev_country": None,
            "device_distinct_cards_lifetime": 1,
        },
        "ml_prob": 0.0,
        "fired_rules": [],
        "decision": "allow",
    }


def _fn_run_record(i: int) -> dict:
    """One FN in the 'new card / new device / electronics' pattern."""
    return _run_record(
        f"fn_{i:03d}",
        delta_minutes=i * 10,
        amount=str(250 + i * 25),
        card_id=f"c_fn_{i}",
        device_id=f"d_fn_{i}",
        merchant_category="electronics",
        card_age_days=i % 25,                # <30 = "new" bucket
        device_seen_before=False,
    )


def _benign_record(i: int) -> dict:
    return _run_record(
        f"benign_{i:03d}",
        delta_minutes=1000 + i * 13,
        amount=str(15 + i * 4),
        card_id=f"c_benign_{i}",
        device_id=f"d_benign_{i}",
        merchant_category="grocery",
        card_age_days=400,
        device_seen_before=True,
    )


def build() -> tuple[list[dict], list[dict]]:
    runs = [_fn_run_record(i) for i in range(7)]
    runs.extend(_benign_record(i) for i in range(20))
    runs.sort(key=lambda r: r["ts"])

    labels = []
    for run in runs:
        txn_id = run["txn"]["txn_id"]
        if txn_id.startswith("fn_"):
            labels.append({
                "txn_id": txn_id,
                "label": "fraud",
                "note": "Brand-new card on a brand-new device, high-value electronics — looks like ATO",
                "labeled_at": run["ts"],
            })
        else:
            labels.append({"txn_id": txn_id, "label": "legit", "note": "", "labeled_at": run["ts"]})
    return runs, labels


def main() -> None:
    runs, labels = build()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)

    log_path = RUNS_DIR / "2026-05-01.jsonl"
    log_path.write_text("\n".join(json.dumps(r) for r in runs) + "\n")
    LABELS_PATH.write_text("\n".join(json.dumps(r) for r in labels) + "\n")

    fns = sum(1 for r in labels if r["label"] == "fraud")
    print(f"wrote {len(runs)} run records + {len(labels)} labels ({fns} fraud)")
    print(f"  runs: {log_path}")
    print(f"  labels: {LABELS_PATH}")


if __name__ == "__main__":
    main()
