"""Build synthetic IEEE-CIS-shape splits (#2).

Generates ~100k transactions over 60 days with a ~3.5% fraud rate and writes
four entity-disjoint Parquet splits:

  train   60%   — fraud-ml training
  replay  15%   — fraud-replay regression corpus
  holdout 15%   — never seen by the reflector or its guards
  stream  10%   — chronological "live" feed for the demo

Entity-level split: a given card_id appears in exactly one split — the AC
explicitly calls out that a row-level random split would leak card-level
patterns into the holdout. Splits are reproducible from RANDOM_SEED.

Fraud is injected with five learnable structural patterns (card-testing,
geo-jump, decline retries, new-device high-value, BIN concentration) plus
some uncategorized noise. These are realistic enough that a GBM trained on
train.parquet learns to flag many of them, but novel scheme injection in
#13 + #14 still produces FNs the reflector needs to catch.

Run: `python data/build_splits.py`
"""

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SPLITS_DIR = REPO_ROOT / "data" / "splits"
SPLITS_DOC = REPO_ROOT / "data" / "SPLITS.md"

RANDOM_SEED = 42
N_TXNS_TARGET = 100_000
N_CARDS = 12_000
N_DEVICES = 8_000
N_MERCHANTS = 1_500
N_DAYS = 60
START = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
FRAUD_RATE = 0.035

COUNTRIES = ["US", "DE", "FR", "GB", "JP", "CA", "AU", "BR", "MX", "NL"]
COUNTRY_PROBS = np.array([0.65, 0.07, 0.05, 0.05, 0.04, 0.04, 0.03, 0.03, 0.02, 0.02])

CATEGORIES = [
    "grocery", "restaurant", "retail-apparel", "retail-electronics",
    "gas", "gaming", "online-cash-out", "subscription", "luxury",
    "travel", "prepaid-card", "gift-card",
]
CATEGORY_PROBS = np.array([0.20, 0.15, 0.12, 0.10, 0.08, 0.05, 0.03, 0.10, 0.04, 0.05, 0.04, 0.04])


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def _rng():
    return np.random.default_rng(RANDOM_SEED)


def _make_entities():
    rng = _rng()
    cards = [f"c_{i:06d}" for i in range(N_CARDS)]
    devices = [f"d_{i:06d}" for i in range(N_DEVICES)]
    merchants = [f"m_{i:05d}" for i in range(N_MERCHANTS)]
    # Each card belongs to a country (most-used country) and has an age.
    card_country = rng.choice(COUNTRIES, size=N_CARDS, p=COUNTRY_PROBS)
    card_age_days = rng.integers(low=1, high=720, size=N_CARDS)
    # Each card has a "favorite" device (90% of txns) and may use others.
    card_fav_device = rng.integers(low=0, high=N_DEVICES, size=N_CARDS)
    # BIN: first 6 digits of a synthetic PAN — ~200 distinct BINs.
    card_bin = rng.choice([f"{b:06d}" for b in range(400000, 400200)], size=N_CARDS)
    return {
        "cards": cards,
        "devices": devices,
        "merchants": merchants,
        "card_country": card_country,
        "card_age_days": card_age_days,
        "card_fav_device": card_fav_device,
        "card_bin": card_bin,
    }


def _amount(rng):
    # Log-normal, clipped to a realistic range
    return float(np.clip(np.exp(rng.normal(3.5, 1.1)), 1, 5000))


def _legit_txn(rng, ent, card_idx, ts) -> dict:
    use_fav = rng.random() < 0.92
    device_idx = ent["card_fav_device"][card_idx] if use_fav else rng.integers(N_DEVICES)
    cat_idx = rng.choice(len(CATEGORIES), p=CATEGORY_PROBS)
    return _row(
        ent, card_idx, device_idx, cat_idx, ts,
        amount=_amount(rng),
        country=ent["card_country"][card_idx],
        approved=rng.random() > 0.04,
        is_fraud=False,
        scheme=None,
    )


def _fraud_card_testing(rng, ent, card_idx, ts):
    cat_idx = CATEGORIES.index("retail-apparel")
    out = []
    for i in range(rng.integers(5, 9)):
        out.append(_row(
            ent, card_idx, rng.integers(N_DEVICES), cat_idx,
            ts + timedelta(seconds=int(i * rng.integers(5, 12))),
            amount=float(rng.uniform(0.5, 4.5)),
            country=ent["card_country"][card_idx],
            approved=rng.random() > 0.4,
            is_fraud=True,
            scheme="card_testing",
        ))
    return out


def _fraud_decline_retry(rng, ent, card_idx, ts):
    cat_idx = rng.choice(len(CATEGORIES))
    out = []
    for i in range(rng.integers(2, 4)):
        out.append(_row(
            ent, card_idx, ent["card_fav_device"][card_idx], cat_idx,
            ts + timedelta(minutes=int(i * 5)),
            amount=_amount(rng),
            country=ent["card_country"][card_idx],
            approved=False, is_fraud=True, scheme="decline_retry",
        ))
    out.append(_row(
        ent, card_idx, ent["card_fav_device"][card_idx], cat_idx,
        ts + timedelta(minutes=20),
        amount=_amount(rng),
        country=ent["card_country"][card_idx],
        approved=True, is_fraud=True, scheme="decline_retry",
    ))
    return out


def _fraud_geo_jump(rng, ent, card_idx, ts):
    home = ent["card_country"][card_idx]
    other = rng.choice([c for c in COUNTRIES if c != home])
    return [
        _row(
            ent, card_idx, ent["card_fav_device"][card_idx], rng.choice(len(CATEGORIES)),
            ts,
            amount=_amount(rng),
            country=home, approved=True, is_fraud=False, scheme=None,
        ),
        _row(
            ent, card_idx, rng.integers(N_DEVICES), rng.choice(len(CATEGORIES)),
            ts + timedelta(minutes=int(rng.integers(2, 25))),
            amount=_amount(rng),
            country=other, approved=True, is_fraud=True, scheme="geo_jump",
        ),
    ]


def _fraud_high_amt_new_device(rng, ent, card_idx, ts):
    return [_row(
        ent, card_idx, rng.integers(N_DEVICES), CATEGORIES.index("retail-electronics"),
        ts,
        amount=float(rng.uniform(600, 2500)),
        country=ent["card_country"][card_idx],
        approved=True, is_fraud=True, scheme="high_amt_new_device",
    )]


def _fraud_bin_concentration(rng, ent, card_idx, ts):
    # Same as fav device, but recognizable-by-BIN-and-cash-out
    return [_row(
        ent, card_idx, rng.integers(N_DEVICES), CATEGORIES.index("online-cash-out"),
        ts,
        amount=float(rng.uniform(150, 500)),
        country=ent["card_country"][card_idx],
        approved=True, is_fraud=True, scheme="bin_concentration",
    )]


def _row(ent, card_idx, device_idx, cat_idx, ts, *, amount, country, approved, is_fraud, scheme):
    return {
        "txn_id": "",  # filled at the end
        "ts": ts,
        "amount": round(amount, 2),
        "currency": "USD",
        "merchant_id": ent["merchants"][int(np.random.randint(N_MERCHANTS))],
        "merchant_category": CATEGORIES[cat_idx],
        "card_id": ent["cards"][card_idx],
        "device_id": ent["devices"][device_idx],
        "ip": f"1.{int(np.random.randint(255))}.{int(np.random.randint(255))}.{int(np.random.randint(255))}",
        "country": country,
        "approved": approved,
        "city": None,
        "bin": ent["card_bin"][card_idx],
        "is_fraud": is_fraud,
        "scheme": scheme or "",
    }


def generate() -> pd.DataFrame:
    rng = _rng()
    np.random.seed(RANDOM_SEED)  # for the random_id calls inside _row
    random.seed(RANDOM_SEED)
    ent = _make_entities()

    rows: list[dict] = []
    txn_count_per_card = rng.integers(low=1, high=40, size=N_CARDS)
    fraud_quota_remaining = int(N_TXNS_TARGET * FRAUD_RATE)

    schedule = []
    for card_idx in range(N_CARDS):
        n = txn_count_per_card[card_idx]
        for _ in range(n):
            schedule.append(card_idx)

    rng.shuffle(schedule)
    schedule = schedule[:N_TXNS_TARGET]

    fraud_handlers = [
        _fraud_card_testing,
        _fraud_decline_retry,
        _fraud_geo_jump,
        _fraud_high_amt_new_device,
        _fraud_bin_concentration,
    ]

    for i, card_idx in enumerate(schedule):
        ts = START + timedelta(seconds=int(rng.uniform(0, N_DAYS * 86400)))
        if fraud_quota_remaining > 0 and rng.random() < FRAUD_RATE * 1.3:
            handler = rng.choice(len(fraud_handlers))
            new = fraud_handlers[handler](rng, ent, card_idx, ts)
            rows.extend(new)
            fraud_quota_remaining -= sum(1 for r in new if r["is_fraud"])
        else:
            rows.append(_legit_txn(rng, ent, card_idx, ts))

    df = pd.DataFrame(rows)
    df["txn_id"] = [f"t_{i:08d}" for i in range(len(df))]
    df.sort_values("ts", inplace=True, kind="mergesort")
    df.reset_index(drop=True, inplace=True)
    return df


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------


SPLIT_RATIOS = {"train": 0.60, "replay": 0.15, "holdout": 0.15, "stream": 0.10}


def split_entity_level(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Assign each card_id to exactly one split, then carry every txn with it."""
    rng = np.random.default_rng(RANDOM_SEED + 1)
    cards = df["card_id"].unique()
    rng.shuffle(cards)
    n = len(cards)
    cuts = {}
    cursor = 0
    for name, frac in SPLIT_RATIOS.items():
        take = int(round(n * frac))
        cuts[name] = set(cards[cursor:cursor + take])
        cursor += take
    # Sweep any rounding remainder into the last split.
    leftover = set(cards[cursor:])
    cuts["stream"] |= leftover

    out = {}
    for name, ids in cuts.items():
        sub = df[df["card_id"].isin(ids)].copy()
        sub.sort_values("ts", inplace=True, kind="mergesort")
        out[name] = sub
    return out


def _write_parquet(splits: dict[str, pd.DataFrame]) -> None:
    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    for name, sub in splits.items():
        sub.to_parquet(SPLITS_DIR / f"{name}.parquet", index=False)


def _write_splits_doc(splits: dict[str, pd.DataFrame]) -> None:
    lines = [
        "# Splits",
        "",
        "Generated by `python data/build_splits.py`. Deterministic from seed "
        f"`{RANDOM_SEED}`. Entity-level (a given `card_id` appears in exactly one split — "
        "this is the leakage guard the AC calls out).",
        "",
        "| Split | Txns | Fraud | Fraud rate | Cards | Time range |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for name, sub in splits.items():
        n = len(sub)
        f = int(sub["is_fraud"].sum())
        cards = sub["card_id"].nunique()
        tmin = sub["ts"].min()
        tmax = sub["ts"].max()
        lines.append(
            f"| {name} | {n} | {f} | {f/n:.2%} | {cards} | {tmin.date()} → {tmax.date()} |"
        )
    lines += [
        "",
        "## Per-scheme breakdown (training only — schemes are not labeled in production)",
        "",
        "| Scheme | Train | Replay | Holdout | Stream |",
        "|---|---:|---:|---:|---:|",
    ]
    schemes = sorted({s for sub in splits.values() for s in sub["scheme"].unique() if s})
    for s in schemes:
        row = [s] + [str(int((sub["scheme"] == s).sum())) for sub in splits.values()]
        lines.append("| " + " | ".join(row) + " |")
    lines += [
        "",
        "## Leakage check",
        "",
        "Each card belongs to one split. The reflector and its guards never see "
        "holdout-set transactions; the orchestrator never trains on replay or "
        "holdout. The training set is what `skills/fraud-ml/train.py` fits.",
    ]
    SPLITS_DOC.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=SPLITS_DIR)
    args = parser.parse_args()
    print(f"Generating ~{N_TXNS_TARGET} txns ...")
    df = generate()
    print(f"  rows={len(df)} fraud={int(df['is_fraud'].sum())} cards={df['card_id'].nunique()}")
    splits = split_entity_level(df)
    _write_parquet(splits)
    _write_splits_doc(splits)
    print(f"Wrote splits to {SPLITS_DIR} and doc to {SPLITS_DOC}")
    print(json.dumps({name: len(sub) for name, sub in splits.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
