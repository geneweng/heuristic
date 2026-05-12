"""Replay harness: stream a labeled set through ml + rules, score per-scheme metrics,
enforce per-scheme recall floors, emit JSON + Markdown reports.

Exits non-zero if any scheme's recall falls below the floor in `floors.yaml`. This is
the HL anti-forgetting guard — wire it into CI on every PR that touches rules or ml.
"""

import argparse
import json
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from fraud_ml import score as ml_score
from metrics import (
    CombinedMetrics,
    ScoredRecord,
    SchemeMetrics,
    compute_combined_metrics,
    compute_scheme_metrics,
)
from registry import _discover, evaluate
from schemas import Transaction, build_context

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPLAY_PATH = REPO_ROOT / "data" / "replay" / "fixture.jsonl"
DEFAULT_FLOORS_PATH = Path(__file__).parent / "floors.yaml"
DEFAULT_REPORT_DIR = REPO_ROOT / "results" / "output"


def _load_records(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def _to_txn(rec: dict) -> Transaction:
    fields = {k: v for k, v in rec.items() if k not in {"true_scheme_id", "is_fraud"}}
    if "amount" in fields and not isinstance(fields["amount"], Decimal):
        fields["amount"] = Decimal(str(fields["amount"]))
    return Transaction(**fields)


def _load_floors(path: Path) -> dict[str, float]:
    """Tiny YAML-ish loader so the harness has no scientific deps for the floors file.

    Accepts lines of the form `scheme_id: 0.8`. Comments (# ...) and blanks are ignored.
    """
    floors: dict[str, float] = {}
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, val = line.split(":", 1)
        floors[key.strip()] = float(val.strip())
    return floors


def _evaluate_stream(records: list[dict]) -> list[ScoredRecord]:
    """Stream records in ts order, building context from prior records on the same card."""
    records_with_txn = [(rec, _to_txn(rec)) for rec in records]
    records_with_txn.sort(key=lambda x: x[1].ts)
    history: list[Transaction] = []
    out: list[ScoredRecord] = []
    for rec, txn in records_with_txn:
        ctx = build_context(history, txn)
        ml = ml_score(txn, ctx)
        fired = evaluate(txn, ctx)
        out.append(
            ScoredRecord(
                true_scheme_id=rec.get("true_scheme_id"),
                is_fraud=bool(rec.get("is_fraud", False)),
                ml_prob=float(ml["prob"]),
                fired_rules=tuple(fired),
            )
        )
        history.append(txn)
    return out


def _write_json_report(
    path: Path,
    schemes: dict[str, SchemeMetrics],
    combined: CombinedMetrics,
    floors: dict[str, float],
    failed: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemes": {
            sid: {
                "precision": m.precision,
                "recall": m.recall,
                "tp": m.tp,
                "fp": m.fp,
                "fn": m.fn,
                "floor": floors.get(sid),
                "below_floor": sid in failed,
            }
            for sid, m in schemes.items()
        },
        "combined": asdict(combined),
        "failed_schemes": failed,
    }
    path.write_text(json.dumps(payload, indent=2))


def _write_md_report(
    path: Path,
    schemes: dict[str, SchemeMetrics],
    combined: CombinedMetrics,
    floors: dict[str, float],
    failed: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Replay report", ""]
    lines.append("## Per-scheme")
    lines.append("")
    lines.append("| Scheme | Precision | Recall | Floor | TP | FP | FN | Status |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for sid, m in schemes.items():
        floor = floors.get(sid)
        status = "**FAIL**" if sid in failed else "ok"
        floor_s = f"{floor:.2f}" if floor is not None else "-"
        lines.append(
            f"| `{sid}` | {m.precision:.2f} | {m.recall:.2f} | {floor_s} | "
            f"{m.tp} | {m.fp} | {m.fn} | {status} |"
        )
    lines.append("")
    lines.append("## Combined")
    lines.append("")
    lines.append(f"- flagged precision: {combined.flagged_precision:.3f}")
    lines.append(f"- flagged recall: {combined.flagged_recall:.3f}")
    lines.append(f"- PR-AUC: {combined.pr_auc:.3f}")
    if failed:
        lines.append("")
        lines.append("## Failures")
        lines.append("")
        for sid in failed:
            m = schemes[sid]
            floor = floors[sid]
            lines.append(f"- `{sid}`: recall {m.recall:.2f} < floor {floor:.2f}")
    path.write_text("\n".join(lines) + "\n")


def run(
    replay_path: Path = DEFAULT_REPLAY_PATH,
    floors_path: Path = DEFAULT_FLOORS_PATH,
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> dict:
    records = _load_records(replay_path)
    scored = _evaluate_stream(records)

    rule_scheme_ids = [r.scheme_id for r in _discover()]
    schemes = compute_scheme_metrics(scored, rule_scheme_ids)
    combined = compute_combined_metrics(scored)

    floors = _load_floors(floors_path)
    failed = [
        sid
        for sid, m in schemes.items()
        if sid in floors and m.recall < floors[sid] - 1e-9
    ]

    _write_json_report(report_dir / "replay_report.json", schemes, combined, floors, failed)
    _write_md_report(report_dir / "replay_report.md", schemes, combined, floors, failed)

    return {
        "status": "fail" if failed else "ok",
        "failed_schemes": failed,
        "schemes": {sid: m.recall for sid, m in schemes.items()},
        "combined": asdict(combined),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--replay", type=Path, default=DEFAULT_REPLAY_PATH)
    p.add_argument("--floors", type=Path, default=DEFAULT_FLOORS_PATH)
    p.add_argument("--out", type=Path, default=DEFAULT_REPORT_DIR)
    args = p.parse_args()
    result = run(args.replay, args.floors, args.out)
    print(json.dumps(result, indent=2))
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
