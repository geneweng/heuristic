"""Runtime orchestrator: stream txns through fraud-ml + fraud-rules, decide, log.

Reads JSONL of transaction records in time order, builds rolling per-card context,
calls the ML + rules skills, picks a block/review/allow decision, and appends a record
to `runs/<date>.jsonl`. The reflector reads these logs later to find what was missed.

Decision policy (deterministic, fixed thresholds — change here only, never per-call):
  - block  if ml_prob > 0.9 OR any fired rule confidence > 0.9
  - review if ml_prob > 0.5 OR any fired rule confidence > 0.5
  - allow  otherwise
"""

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fraud_ml import score as ml_score
from registry import evaluate
from schemas import Transaction, build_context

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPO_ROOT / "data" / "replay" / "fixture.jsonl"
DEFAULT_RUNS_DIR = REPO_ROOT / "runs"

BLOCK_THRESHOLD = 0.9
REVIEW_THRESHOLD = 0.5


@dataclass(frozen=True)
class Decision:
    decision: str  # "block" | "review" | "allow"
    ml_prob: float
    fired_rules: tuple[tuple[str, float], ...]


def decide(ml_prob: float, fired_rules: list[tuple[str, float]]) -> Decision:
    rule_max = max((c for _, c in fired_rules), default=0.0)
    top = max(ml_prob, rule_max)
    if top > BLOCK_THRESHOLD:
        d = "block"
    elif top > REVIEW_THRESHOLD:
        d = "review"
    else:
        d = "allow"
    return Decision(decision=d, ml_prob=ml_prob, fired_rules=tuple(fired_rules))


def _to_txn(rec: dict) -> Transaction:
    fields = {k: v for k, v in rec.items() if k not in {"true_scheme_id", "is_fraud"}}
    if "amount" in fields and not isinstance(fields["amount"], Decimal):
        fields["amount"] = Decimal(str(fields["amount"]))
    return Transaction(**fields)


def _load_records(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def _runs_path(runs_dir: Path, now: datetime) -> Path:
    return runs_dir / f"{now.strftime('%Y-%m-%d')}.jsonl"


def run(
    input_path: Path = DEFAULT_INPUT,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    now_factory=lambda: datetime.now(timezone.utc),
) -> dict:
    """Stream input_path through the decision pipeline; append to runs/<date>.jsonl.

    `now_factory` is overrideable so tests can pin the decision timestamp.
    """
    records = _load_records(input_path)
    records_with_txn = [(rec, _to_txn(rec)) for rec in records]
    records_with_txn.sort(key=lambda x: x[1].ts)

    history: list[Transaction] = []
    counts = {"block": 0, "review": 0, "allow": 0}
    runs_dir.mkdir(parents=True, exist_ok=True)
    log_path = _runs_path(runs_dir, now_factory())

    with log_path.open("a") as f:
        for _rec, txn in records_with_txn:
            ctx = build_context(history, txn)
            ml = ml_score(txn, ctx)
            fired = evaluate(txn, ctx)
            d = decide(ml["prob"], fired)
            counts[d.decision] += 1
            f.write(
                json.dumps(
                    {
                        "ts": now_factory().isoformat(),
                        "txn": json.loads(txn.model_dump_json()),
                        "ctx": json.loads(ctx.model_dump_json()),
                        "ml_prob": d.ml_prob,
                        "fired_rules": [list(r) for r in d.fired_rules],
                        "decision": d.decision,
                    }
                )
                + "\n"
            )
            history.append(txn)

    return {"processed": len(records_with_txn), "counts": counts, "log": str(log_path)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    args = p.parse_args()
    result = run(args.input, args.runs_dir)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
