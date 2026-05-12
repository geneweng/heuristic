---
layout: default
title: Demo Scenario — The BIN-654321 attack
---

# Demo Scenario — "The BIN-654321 attack"

A walkthrough of what this POC does in practice, framed as one realistic
incident. Drawn from the synthetic data + injectors that ship in the repo, so
every artifact below can be reproduced end-to-end with `make`.

## The setup (day 0)

A mid-tier card issuer is running the system in production:

- **Frozen GBM** ([`skills/fraud-ml`](https://github.com/geneweng/heuristic/tree/main/skills/fraud-ml))
  trained on 60 days of history. AUC 0.998 on a held-out slice. Strong but
  brittle to schemes it didn't see in training.
- **Five human-authored rules** ([`skills/fraud-rules/rules`](https://github.com/geneweng/heuristic/tree/main/skills/fraud-rules/rules))
  for known patterns: card-testing bursts, impossible geo-velocity,
  decline-retry, new-device-aged-card, device-shared-across-cards.
- **Replay floors** ([`skills/fraud-replay/floors.yaml`](https://github.com/geneweng/heuristic/blob/main/skills/fraud-replay/floors.yaml))
  gate every rule change: drop recall on any prior scheme below its floor and
  CI fails. This is the anti-forgetting guard.
- **A reflector skill** ([`skills/fraud-reflector`](https://github.com/geneweng/heuristic/tree/main/skills/fraud-reflector))
  sleeping; runs nightly.

Volume: tens of thousands of auths a day. Detection rate is steady. Nobody
is touching the ML model.

## Day 3 — A new scheme starts

A fraud ring lights up a freshly-issued BIN range (`654321xxxxxx`). They use
stolen card numbers from that BIN for online cash-out at $199 each, routing
through merchants in Austria (`country=AT`,
`merchant_category=online-cash-out`).

The ML didn't see this BIN at training time. The seed rules don't match
either — there's no count-based burst, no geo-velocity, no decline retry,
the cards aren't aged, and there's no device-ring topology. **Seven of
these auths approve. None are flagged.**

The injector that produces this scheme lives at
[`data/injectors/new_bin_attack.py`](https://github.com/geneweng/heuristic/blob/main/data/injectors/new_bin_attack.py). The
relevant generated row in the run log looks like:

```jsonc
{
  "ts": "2026-05-04T09:00:00Z",
  "txn": {"txn_id": "inj_nba_000", "amount": "199.00", "currency": "USD",
          "merchant_id": "m_oco_0", "merchant_category": "online-cash-out",
          "card_id": "c_nba_0", "device_id": "d_nba_0",
          "country": "AT", "bin": "654321", "approved": true, ...},
  "ctx": {"card_age_days": 14, "current_device_seen_before_for_card": false, ...},
  "ml_prob": 0.0,                  // ← frozen ML misses
  "fired_rules": [],               // ← no seed rule matches
  "decision": "allow"              // ← let through
}
```

## Day 4 morning — A fraud analyst notices

A chargeback comes in for one of the BIN-654321 txns. The analyst opens the
Streamlit UI (`make ui`), filters by merchant_category, finds six more, and
labels each `fraud` with a note:

> "Brand-new BIN, suspicious cash-out, AT corridor — looks like a new
> issuer-laundering pattern."

The UI appends to `labels/labels.jsonl`. The reflector reads this file.

## Day 4 evening — The reflector wakes

`make reflect` runs on the nightly cron. The loop:

1. **Find FNs** — `decision=allow` ∩ `label=fraud` → 7 records from the BIN
   attack.
2. **Cluster by feature bucket** — `(country=AT, merchant_category=online-cash-out,
   card_age=new, device=newdev, amount=mid)`. All seven land in one cluster.
3. **Skip-rejection check** — no prior rejection for this cluster fingerprint
   ([`rejections.should_skip_cluster`](https://github.com/geneweng/heuristic/blob/main/skills/fraud-reflector/rejections.py)).
4. **Validate the cluster** — ≥5 FNs, distinct cards, distinct merchants ✓
   ([`clusters.validate_cluster`](https://github.com/geneweng/heuristic/blob/main/skills/fraud-reflector/clusters.py)).
5. **Prompt Claude** with [`propose_rule.md`](https://github.com/geneweng/heuristic/blob/main/skills/fraud-reflector/prompts/propose_rule.md) +
   the cluster JSON + the schemas + the existing rule list. Tool-use only,
   no free-text parsing.
6. **Run the four guards** ([`guards.py`](https://github.com/geneweng/heuristic/blob/main/skills/fraud-reflector/guards.py)):
   no identity-feature literals, holdout precision ≥ 0.85, FP rate on legit
   ≤ 0.1%, no existing rule already covers > 70% of the cited FNs.
7. **Materialize** the rule as `skills/fraud-rules/rules/bin_654321_at_cashout_v1.py`
   plus its test file.
8. **Run replay** — all five prior schemes still at their floor. No regression.
9. **Open a PR** with the [reflector template](https://github.com/geneweng/heuristic/blob/main/.github/PULL_REQUEST_TEMPLATE/reflector.md).
10. **Log the attempt** to `memory/attempts.jsonl`.

The rule file Claude produced — auditable Python an analyst can read:

```python
"""BIN-range cash-out abuse (v1).

A freshly-issued BIN range (`654321xxx`) being used for low-amount
online-cash-out auths in non-home countries. Pattern: card_age_days < 30,
country mismatch from typical issuer footprint, merchant_category
'online-cash-out', amount clustering around $199. Stolen-PAN laundering
through a new issuer the ML didn't see at training time.
"""

from decimal import Decimal
from schemas import EntityContext, Transaction

scheme_id = "bin_654321_at_cashout_v1"
confidence = 0.92
created_at = "2026-05-04"
author = "reflector"


def applies(txn: Transaction, ctx: EntityContext) -> bool:
    return (
        txn.bin == "654321"
        and txn.merchant_category == "online-cash-out"
        and txn.country == "AT"
        and ctx.card_age_days < 30
        and Decimal("150") <= txn.amount <= Decimal("250")
    )
```

(Predicate shape and exact thresholds depend on what Claude proposes; the
shape above is illustrative of what the live prompt has been tuned to
produce. The dry-run `stub_propose` produces a structurally similar rule
without an API call — useful for CI.)

## Day 4 PR review

The PR body (rendered from
[`.github/PULL_REQUEST_TEMPLATE/reflector.md`](https://github.com/geneweng/heuristic/blob/main/.github/PULL_REQUEST_TEMPLATE/reflector.md))
lists:

- The scheme description Claude wrote
- The seven cited txn IDs
- A checklist of pre-merge checks (all already passed)
- An embedded machine-parseable metadata block — `(cluster_id, scheme_id, fn_count, cited_txn_ids)`

Two things matter here:

- **CODEOWNERS gates the merge.** Per [`.github/CODEOWNERS`](https://github.com/geneweng/heuristic/blob/main/.github/CODEOWNERS),
  any change under `skills/fraud-rules/rules/**` requires a human reviewer.
  Reflector PRs cannot self-merge.
- **Rejecting writes to memory.** If the analyst clicks Reject in the UI, the
  metadata block is parsed and a record lands in `memory/rejections.jsonl`.
  The reflector won't re-propose this cluster for 14 days unless the FN count
  doubles.

The analyst approves. The rule goes live. The eighth BIN-654321 auth that
arrives that evening is blocked.

## Day 5 onward — Steady state

- **Recall on the BIN scheme jumps from 0 → 1.0** within hours of the first
  labeled FN.
- **Recall on the five seed schemes stays flat at 1.0.** Verified every PR by
  `make replay` against `floors.yaml`.
- **The ML never retrained.** Same model file, same AUC.

The [headline chart](./results/output/headline.png) (run `make results` to
regenerate) shows three injected schemes go from 0 → 1.0 within ~1 simulated
day each, with no dip on the seed schemes.

## What didn't happen (the anti-pattern)

For contrast, here's the path a traditional ML-only stack would have taken:

| Step | ML-retraining shop | This POC |
|---|---|---|
| Detect the new scheme | Wait for enough labeled data, weeks | Hours, on first label |
| Encode the pattern | Retrain → A/B test → roll out, ~1 month | One PR review |
| Audit trail | "the model learned X" (opaque) | `git blame` on a rule file |
| Regression risk | Unknown until A/B | Hard-gated by `floors.yaml` in CI |
| Stakeholder readability | None | Plain-English docstring per rule |

The HL paper's framing: *anything you can continuously iterate on starts to
become solvable*. Fraud schemes are the canonical example — they appear
faster than any retraining cadence, and the cost of a wrong rule is bounded
by a CODEOWNERS-gated PR and a hard regression test.

## Try it yourself

```bash
make install            # editable install
make data               # generate the synthetic splits
make ml-train           # train the frozen GBM (writes model.joblib + BASELINE.md)
make stream             # orchestrator decides on the seed fixture
make replay             # rule regression check; exits 1 on any floor break
make reflect            # offline reflector loop (no API key needed)
make results            # 14-day simulation; produces SUMMARY.md + headline.png
make ui                 # Streamlit analyst UI on localhost:8501
```

For the live reflector (real Claude, real PR):

```bash
ANTHROPIC_API_KEY=sk-... python -m reflector --live --open-pr
```

## What's behind the curtain (mapped to the HL paper)

| HL paper concept | This repo |
|---|---|
| Programmatic policy | `skills/fraud-rules/` |
| State representation | `Transaction`, `EntityContext` in `skills/common/schemas.py` |
| Feedback channels | `labels/labels.jsonl` (the analyst UI writes) |
| Experiment records | `runs/<date>.jsonl` (the orchestrator writes) |
| Replays / tests | `skills/fraud-replay/` + `floors.yaml` |
| Memory | `memory/{attempts,rejections}.jsonl` |
| Update mechanism | `skills/fraud-reflector/` — Claude tool_use + guards + PR |

The "update mechanism" is the only part that's gradient-free in the
operationally-interesting sense. Everything else — the ML, the rules, the
test corpus, the analyst's labels — is conventional infrastructure. The
novelty is that the *update* to the policy is mediated by an LLM coding
agent writing Python in PR form, not a backpropagation step.

## What the POC doesn't try to prove

- That HL beats every ML retraining setup on raw detection. It doesn't —
  ML still does most of the heavy lifting.
- That LLM-written rules are perfect. They aren't — that's what the four
  guards (`identity_features`, `holdout_precision`, `fp_cap`, `redundancy`)
  and the human reviewer are for.
- That you can drop this into production tomorrow. Sandboxing the predicate
  exec, hardening the gh wrappers, real Kaggle/IEEE-CIS data swap, and
  Anthropic-API rate-limit handling are all real work past where the POC
  stops.

The thesis the POC *does* prove: when a novel scheme appears, the system
detects it, encodes it as a reviewable rule, and ships it within a
business day — without retraining and without forgetting what it already
knew. That story holds end-to-end in the headline simulation.
