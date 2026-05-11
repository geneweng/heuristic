"""Reflector prompt evaluation harness.

Two modes:
- **dry-run** (default): builds the full prompt for a cluster and validates that it
  contains the cluster, the schema docs, and the existing-rule context. No API call.
- **live**: hits Claude with the prompt + tool definitions and returns the parsed
  tool call. Requires ANTHROPIC_API_KEY. Gated behind the `--live` flag.

The seed corpus is `eval_clusters/*.json`. Ship 5 to start (3 valid + 2 adversarial);
the AC calls for 20 — track progress in `eval_clusters/README.md`.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from clusters import (
    FNCluster,
    load_all_clusters,
    load_cluster,
    validate_cluster,
)
from registry import _discover
from tool_schema import REFLECTOR_TOOLS

PROMPT_PATH = Path(__file__).parent / "prompts" / "propose_rule.md"
CLUSTERS_DIR = Path(__file__).parent / "eval_clusters"
MODEL = "claude-opus-4-7"

SCHEMA_DOCS = """
### Transaction
- txn_id, ts, amount, currency, merchant_id, merchant_category, card_id,
  device_id, ip, country, approved, city, bin

### EntityContext (per-card aggregates at decision time)
- card_txn_count_24h, card_amount_24h, card_distinct_merchants_24h,
  card_distinct_devices_lifetime, card_seconds_since_last_txn,
  card_decline_count_1h, card_age_days, card_txn_count_60s,
  card_min_amount_60s, current_device_seen_before_for_card, prev_country,
  device_distinct_cards_lifetime

Identity features banned in rule predicates: card_id, txn_id, merchant_id,
device_id, ip, bin (any string literal from a single txn).
""".strip()


def _format_existing_rules() -> str:
    rules = _discover()
    if not rules:
        return "_(none yet)_"
    return "\n".join(
        f"- `{r.scheme_id}` (conf {r.confidence}): {r.applies.__module__.split('.')[-1]}"
        for r in rules
    )


def _cluster_to_prompt_dict(c: FNCluster) -> dict:
    return {
        "cluster_id": c.cluster_id,
        "analyst_summary": c.analyst_summary,
        "fn_records": [
            {"txn_id": r.txn_id, "txn": r.txn, "ctx": r.ctx, "analyst_note": r.analyst_note}
            for r in c.fn_records
        ],
    }


def build_prompt(cluster: FNCluster) -> str:
    """Compose the static prompt + dynamic context for one cluster."""
    parts = [
        PROMPT_PATH.read_text(),
        "## Schemas",
        SCHEMA_DOCS,
        "## Existing rules (do not duplicate)",
        _format_existing_rules(),
        "## Cluster",
        json.dumps(_cluster_to_prompt_dict(cluster), indent=2),
    ]
    return "\n\n".join(parts)


def propose_rule(cluster: FNCluster, *, live: bool = False, model: str = MODEL) -> dict:
    """Run the prompt for one cluster. Defaults to dry-run."""
    issues = validate_cluster(cluster)
    if issues:
        return {
            "cluster_id": cluster.cluster_id,
            "action": "rejected_by_validator",
            "issues": issues,
        }

    prompt = build_prompt(cluster)
    if not live:
        return {
            "cluster_id": cluster.cluster_id,
            "action": "dry_run",
            "prompt_chars": len(prompt),
            "tools": [t["name"] for t in REFLECTOR_TOOLS],
        }

    # Live mode: only imported when needed so dry-run has no SDK dep.
    import anthropic  # noqa: F401  (kept local to avoid hard dep)

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=4000,
        tools=REFLECTOR_TOOLS,
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": prompt}],
    )
    tool_calls = [b for b in resp.content if b.type == "tool_use"]
    if not tool_calls:
        return {"cluster_id": cluster.cluster_id, "action": "no_tool_call"}
    tc = tool_calls[0]
    return {
        "cluster_id": cluster.cluster_id,
        "action": tc.name,
        "input": tc.input,
        "stop_reason": resp.stop_reason,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cluster", type=Path, help="One cluster JSON (default: all)")
    p.add_argument("--live", action="store_true", help="Hit Claude (needs ANTHROPIC_API_KEY)")
    p.add_argument("--model", default=MODEL)
    args = p.parse_args()

    if args.live and "ANTHROPIC_API_KEY" not in os.environ:
        print("ANTHROPIC_API_KEY not set; --live aborted", file=sys.stderr)
        return 2

    clusters = [load_cluster(args.cluster)] if args.cluster else load_all_clusters(CLUSTERS_DIR)
    results = [propose_rule(c, live=args.live, model=args.model) for c in clusters]
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
