"""Reflector loop: runs/ + labels/ → clusters → propose → guards → materialize → PR.

The HL paper's "update mechanism." Reads experiment records from a run log,
finds confirmed false negatives via the labels file, groups them by feature
bucket, and asks a coding agent to propose a new rule per cluster. Every
proposal — accepted or rejected — appends to `memory/attempts.jsonl` so
future runs avoid retreading the same ground.

## Modes

- **dry-run** (`live=False`, default): uses a stub proposer; safe for CI and
  for exercising the pipeline without an API key. Materializes proposed rules
  to `proposals/` so nothing lands in `skills/fraud-rules/rules/`.
- **live** (`live=True`, requires `ANTHROPIC_API_KEY`): hits Claude with the
  propose_rule tool; materializes to the live rules dir.
- **open_pr** (`open_pr=True`): also opens a GitHub PR via `gh`. Off by default.

## CLI

```bash
make reflect              # dry-run against the reflect fixture
python -m reflector --runs runs --labels labels/labels.jsonl --live --open-pr
```
"""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable

from clustering import cluster_fns
from clusters import FNCluster, FNRecord, validate_cluster
from cost import Usage
from eval import build_prompt
from guards import (
    ExistingRule,
    GuardConfig,
    GuardFloors,
    LabeledRecord,
    log_attempt,
    validate_proposal,
)
from materialize import materialize_rule
from registry import _discover
from schemas import EntityContext, Transaction
from tool_schema import REFLECTOR_TOOLS

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS_DIR = REPO_ROOT / "runs"
DEFAULT_LABELS = REPO_ROOT / "labels" / "labels.jsonl"
DEFAULT_PROPOSALS_DIR = REPO_ROOT / "proposals"
LIVE_RULES_DIR = REPO_ROOT / "skills" / "fraud-rules" / "rules"
LIVE_TESTS_DIR = REPO_ROOT / "skills" / "fraud-rules" / "tests"
DEFAULT_MODEL = "claude-opus-4-7"


@dataclass(frozen=True)
class ReflectorReport:
    clusters_found: int
    clusters_processed: int
    results: list[dict]
    total_usage: dict


# --- FN finding ---------------------------------------------------------------


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def find_false_negatives(runs_dir: Path, labels_path: Path) -> list[FNRecord]:
    """Join runs/*.jsonl with labels.jsonl; return FNs (allow decision + fraud label).

    Labels file format: one JSON per line with at least
      {"txn_id": str, "label": "fraud"|"legit"|"unsure", "note": str?}
    """
    label_by_id: dict[str, dict] = {}
    for rec in _load_jsonl(labels_path):
        label_by_id[rec["txn_id"]] = rec

    fns: list[FNRecord] = []
    for run_file in sorted(runs_dir.glob("*.jsonl")):
        for rec in _load_jsonl(run_file):
            txn = rec.get("txn", {})
            txn_id = txn.get("txn_id")
            if not txn_id:
                continue
            label = label_by_id.get(txn_id)
            if not label or label.get("label") != "fraud":
                continue
            if rec.get("decision") != "allow":
                continue
            fns.append(
                FNRecord(
                    txn_id=txn_id,
                    txn=txn,
                    ctx=rec.get("ctx", {}),
                    analyst_note=label.get("note", ""),
                )
            )
    return fns


# --- proposers ----------------------------------------------------------------


def stub_propose(cluster: FNCluster, *, model: str = DEFAULT_MODEL) -> dict:
    """Deterministic offline proposer used in dry-run.

    Synthesizes a defensible proposal from the cluster's shared bucket so the
    rest of the pipeline (guards + materialize + replay) can be exercised end-to-
    end without an API call. The proposal won't always pass the production guards
    — that's fine; the point is to walk the pipeline.
    """
    sample = cluster.fn_records[0]
    txn = sample.txn
    ctx = sample.ctx
    cited = [r.txn_id for r in cluster.fn_records[:5]]

    age_bucket = ctx.get("card_age_days", 0)
    new_dev = not ctx.get("current_device_seen_before_for_card", True)
    amount = Decimal(str(txn.get("amount", "0")))

    pred_parts = []
    if new_dev:
        pred_parts.append("not ctx.current_device_seen_before_for_card")
    if age_bucket < 30:
        pred_parts.append("ctx.card_age_days < 30")
    if amount > 100:
        pred_parts.append(f"txn.amount > Decimal('{int(amount) // 2}')")
    pred_parts.append(f"txn.country == {txn.get('country', 'US')!r}")
    pred_parts.append(f"txn.merchant_category == {txn.get('merchant_category', '')!r}")
    predicate_code = "return " + " and ".join(pred_parts)

    scheme_id = f"reflector_{cluster.cluster_id[:30]}_v1".lower().replace("-", "_")

    return {
        "action": "propose_rule",
        "input": {
            "scheme_id": scheme_id,
            "description": (
                f"Reflector proposal from {cluster.cluster_id}. "
                f"Catches transactions matching the cluster's shared bucket: "
                f"{cluster.analyst_summary}"
            ),
            "rationale": "Stub proposer; structural features only.",
            "predicate_code": predicate_code,
            "positive_tests": [
                {
                    "txn_overrides": {"amount": str(amount)},
                    "ctx_overrides": {
                        "card_age_days": ctx.get("card_age_days", 0),
                        "current_device_seen_before_for_card": ctx.get(
                            "current_device_seen_before_for_card", False
                        ),
                    },
                    "expected_fire": True,
                }
                for _ in range(3)
            ],
            "negative_tests": [
                {
                    "txn_overrides": {"amount": "10"},
                    "ctx_overrides": {
                        "card_age_days": 500,
                        "current_device_seen_before_for_card": True,
                    },
                    "expected_fire": False,
                }
                for _ in range(3)
            ],
            "cited_txn_ids": cited,
            "confidence": 0.7,
        },
        "usage": Usage(model=model, input_tokens=0, output_tokens=0),
    }


def live_propose(cluster: FNCluster, *, model: str = DEFAULT_MODEL) -> dict:
    """Live proposer: hits Claude with propose_rule + decline_rule_proposal tools."""
    import anthropic

    client = anthropic.Anthropic()
    prompt = build_prompt(cluster)
    resp = client.messages.create(
        model=model,
        max_tokens=4000,
        tools=REFLECTOR_TOOLS,
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": prompt}],
    )
    usage = Usage(
        model=model,
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
    )
    tool_calls = [b for b in resp.content if b.type == "tool_use"]
    if not tool_calls:
        return {"action": "no_tool_call", "usage": usage}
    tc = tool_calls[0]
    return {"action": tc.name, "input": dict(tc.input), "usage": usage}


# --- the loop -----------------------------------------------------------------


def _build_guard_config(cluster: FNCluster, *, holdout: list[LabeledRecord], legit: list[LabeledRecord]) -> GuardConfig:
    """Materialize the guard inputs the proposed rule will be tested against."""
    existing = [ExistingRule(scheme_id=r.scheme_id, applies=r.applies) for r in _discover()]
    cited_labeled = [
        LabeledRecord(
            txn=_record_to_txn(r.txn),
            ctx=_record_to_ctx(r.ctx),
            true_scheme_id=None,
            is_fraud=True,
        )
        for r in cluster.fn_records
    ]
    return GuardConfig(
        holdout=holdout,
        legit=legit,
        existing_rules=existing,
        cited_records=cited_labeled,
    )


def _record_to_txn(rec: dict) -> Transaction:
    base = dict(
        txn_id=rec.get("txn_id", "x"),
        ts=datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc),
        amount=Decimal(str(rec.get("amount", "10.00"))),
        currency=rec.get("currency", "USD"),
        merchant_id=rec.get("merchant_id", "m"),
        merchant_category=rec.get("merchant_category", "grocery"),
        card_id=rec.get("card_id", "c"),
        device_id=rec.get("device_id", "d"),
        ip=rec.get("ip", "0.0.0.0"),
        country=rec.get("country", "US"),
        approved=rec.get("approved", True),
    )
    return Transaction(**base)


def _record_to_ctx(rec: dict) -> EntityContext:
    fields = {}
    for k, v in rec.items():
        if v is None:
            continue
        if k in {"card_amount_24h", "card_min_amount_60s"}:
            fields[k] = Decimal(str(v))
        else:
            fields[k] = v
    return EntityContext(**fields)


def _default_open_pr(scheme_id: str, rule_path: Path, test_path: Path, proposal: dict) -> str:
    branch = f"reflector/{scheme_id}"
    subprocess.run(["git", "checkout", "-b", branch], check=True)
    subprocess.run(["git", "add", str(rule_path), str(test_path)], check=True)
    msg = f"reflector: propose {scheme_id}\n\n{proposal['description']}"
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-m", msg], check=True)
    subprocess.run(["git", "push", "-u", "origin", branch], check=True)
    body = (
        f"## Scheme\n\n`{scheme_id}` — confidence {proposal['confidence']}\n\n"
        f"## Description\n\n{proposal['description']}\n\n"
        f"## Rationale\n\n{proposal['rationale']}\n\n"
        f"## Cited evidence\n\n{', '.join(proposal['cited_txn_ids'])}\n"
    )
    result = subprocess.run(
        ["gh", "pr", "create", "--title", f"reflector: {scheme_id}", "--body", body],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def reflect(
    *,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    labels_path: Path = DEFAULT_LABELS,
    rules_dir: Path | None = None,
    tests_dir: Path | None = None,
    holdout: list[LabeledRecord] | None = None,
    legit: list[LabeledRecord] | None = None,
    live: bool = False,
    open_pr: bool = False,
    max_clusters: int = 5,
    propose_fn: Callable[[FNCluster], dict] | None = None,
    replay_fn: Callable[[], bool] = lambda: True,
    pr_fn: Callable | None = None,
    attempts_log: Path | None = None,
    today: date | None = None,
    min_cluster_size: int = 5,
) -> ReflectorReport:
    """Run the reflector loop end-to-end. See module docstring for modes."""
    rules_dir = rules_dir or (LIVE_RULES_DIR if live else DEFAULT_PROPOSALS_DIR / "rules")
    tests_dir = tests_dir or (LIVE_TESTS_DIR if live else DEFAULT_PROPOSALS_DIR / "tests")
    propose_fn = propose_fn or (live_propose if live else stub_propose)
    pr_fn = pr_fn or _default_open_pr
    holdout = holdout or []
    legit = legit or []

    fns = find_false_negatives(runs_dir, labels_path)
    clusters = cluster_fns(fns, min_size=min_cluster_size)
    results: list[dict] = []
    total_in = total_out = 0
    cost = 0.0

    for cluster in clusters[:max_clusters]:
        outcome: dict = {"cluster_id": cluster.cluster_id, "fn_count": len(cluster.fn_records)}

        cluster_issues = validate_cluster(cluster)
        if cluster_issues:
            outcome.update(action="rejected_by_validator", issues=cluster_issues)
            results.append(outcome)
            continue

        proposal_result = propose_fn(cluster)
        usage: Usage = proposal_result.get("usage", Usage(DEFAULT_MODEL, 0, 0))
        total_in += usage.input_tokens
        total_out += usage.output_tokens
        cost += usage.cost_usd

        if proposal_result["action"] != "propose_rule":
            outcome.update(action=proposal_result["action"], usage=usage.as_dict())
            results.append(outcome)
            continue

        proposal = proposal_result["input"]
        guard_cfg = _build_guard_config(cluster, holdout=holdout, legit=legit)
        issues = validate_proposal(proposal, guard_cfg)
        log_attempt(proposal, issues, path=attempts_log or _default_attempts_log())

        if issues:
            outcome.update(action="blocked_by_guards", issues=issues, usage=usage.as_dict())
            results.append(outcome)
            continue

        rule_path, test_path = materialize_rule(
            proposal, rules_dir, tests_dir, today=today or date.today()
        )

        if not replay_fn():
            rule_path.unlink(missing_ok=True)
            test_path.unlink(missing_ok=True)
            log_attempt(
                proposal,
                [{"guard": "replay", "message": "regression after materialize"}],
                path=attempts_log or _default_attempts_log(),
            )
            outcome.update(action="reverted_after_replay_regression", usage=usage.as_dict())
            results.append(outcome)
            continue

        outcome.update(
            action="materialized",
            rule_path=str(rule_path),
            test_path=str(test_path),
            usage=usage.as_dict(),
        )

        if open_pr:
            pr_url = pr_fn(proposal["scheme_id"], rule_path, test_path, proposal)
            outcome["pr"] = pr_url
            outcome["action"] = "pr_opened"

        results.append(outcome)

    return ReflectorReport(
        clusters_found=len(clusters),
        clusters_processed=min(len(clusters), max_clusters),
        results=results,
        total_usage={
            "input_tokens": total_in,
            "output_tokens": total_out,
            "cost_usd": round(cost, 6),
        },
    )


def _default_attempts_log() -> Path:
    return REPO_ROOT / "memory" / "attempts.jsonl"


def run() -> dict:
    """Stub-compatible entry; preserved for callers used to the original stub."""
    return {"status": "noop", "proposals": []}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=Path, default=DEFAULT_RUNS_DIR)
    p.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    p.add_argument("--rules-dir", type=Path)
    p.add_argument("--tests-dir", type=Path)
    p.add_argument("--max-clusters", type=int, default=5)
    p.add_argument("--min-cluster-size", type=int, default=5)
    p.add_argument("--live", action="store_true")
    p.add_argument("--open-pr", action="store_true")
    args = p.parse_args()

    if args.live and "ANTHROPIC_API_KEY" not in os.environ:
        print("ANTHROPIC_API_KEY not set; --live aborted", file=sys.stderr)
        return 2

    report = reflect(
        runs_dir=args.runs,
        labels_path=args.labels,
        rules_dir=args.rules_dir,
        tests_dir=args.tests_dir,
        live=args.live,
        open_pr=args.open_pr,
        max_clusters=args.max_clusters,
        min_cluster_size=args.min_cluster_size,
    )
    print(json.dumps(asdict(report), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
