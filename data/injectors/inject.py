"""CLI to compose injectors into a runs + labels pair.

Usage:
    python -m inject --schemes new_bin_attack,session_replay --start-day 3 \
        --runs runs/sim.jsonl --labels labels/sim_labels.jsonl
"""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from data.injectors import INJECTORS

BASE = datetime(2026, 5, 1, 9, 0, 0, tzinfo=timezone.utc)


def compose(
    schemes: list[str],
    start_day: int = 3,
    day_offset_per_scheme: int = 2,
) -> tuple[list[dict], list[dict]]:
    """Return (runs, labels) lists with each scheme injected on its own day."""
    runs: list[dict] = []
    labels: list[dict] = []
    for i, scheme in enumerate(schemes):
        injector = INJECTORS[scheme]
        day = start_day + i * day_offset_per_scheme
        start_ts = BASE + timedelta(days=day)
        for rr, lr in injector(start_ts):
            runs.append(rr)
            labels.append(lr)
    runs.sort(key=lambda r: r["ts"])
    labels.sort(key=lambda l: l["labeled_at"])
    return runs, labels


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--schemes", default=",".join(INJECTORS.keys()))
    p.add_argument("--start-day", type=int, default=3)
    p.add_argument("--runs", type=Path, required=True)
    p.add_argument("--labels", type=Path, required=True)
    args = p.parse_args()

    schemes = [s.strip() for s in args.schemes.split(",") if s.strip()]
    unknown = [s for s in schemes if s not in INJECTORS]
    if unknown:
        raise SystemExit(f"unknown schemes: {unknown}; valid: {list(INJECTORS)}")

    runs, labels = compose(schemes, start_day=args.start_day)
    args.runs.parent.mkdir(parents=True, exist_ok=True)
    args.labels.parent.mkdir(parents=True, exist_ok=True)
    args.runs.write_text("\n".join(json.dumps(r) for r in runs) + "\n")
    args.labels.write_text("\n".join(json.dumps(l) for l in labels) + "\n")
    print(f"wrote {len(runs)} runs and {len(labels)} labels for schemes={schemes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
