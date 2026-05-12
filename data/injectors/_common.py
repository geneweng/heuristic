"""Shared helpers for injector modules.

Each injector returns a list of (run_record, label_record) tuples in the same
shape that `data/reflect/build_fixture.py` produces, so the reflector loop
consumes them without changes.
"""

from datetime import datetime, timedelta, timezone


def run_record(
    txn_id: str,
    *,
    ts: datetime,
    amount: str,
    card_id: str,
    device_id: str,
    merchant_id: str,
    merchant_category: str,
    country: str,
    bin: str | None = None,
    ip: str = "1.2.3.4",
    ctx: dict | None = None,
) -> dict:
    return {
        "ts": ts.isoformat(),
        "txn": {
            "txn_id": txn_id,
            "ts": ts.isoformat(),
            "amount": amount,
            "currency": "USD",
            "merchant_id": merchant_id,
            "merchant_category": merchant_category,
            "card_id": card_id,
            "device_id": device_id,
            "ip": ip,
            "country": country,
            "approved": True,
            "city": None,
            "bin": bin,
        },
        "ctx": ctx or {},
        "ml_prob": 0.0,
        "fired_rules": [],
        "decision": "allow",
    }


def label_record(txn_id: str, *, scheme_id: str, note: str, ts: datetime) -> dict:
    return {
        "txn_id": txn_id,
        "label": "fraud",
        "scheme_id": scheme_id,
        "note": note,
        "labeled_at": (ts + timedelta(hours=12)).isoformat(),
    }
