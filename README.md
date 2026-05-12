# Heuristic Learning — Fraud Detection POC

A working proof-of-concept for **Heuristic Learning** ([Trinkle, *Learning
Beyond Gradients*](https://trinkle23897.github.io/learning-beyond-gradients/))
applied to fraud detection. Instead of retraining a model when a new fraud
scheme appears, an LLM coding agent reads the run log, clusters missed cases,
and **writes a new human-readable rule** as a PR for an analyst to approve.

The thesis: when a novel fraud scheme is injected, the system detects it
**within hours of the first labeled false negative**, encodes it as a
plain-English rule, and ships it without regressing on prior schemes — the
HL paper's "continual learning without catastrophic forgetting" claim.

## The loop

```
   ┌──────────────┐    runs/    ┌──────────────┐
   │ orchestrator │────────────▶│  analyst UI  │
   └──────▲───────┘             └──────┬───────┘
          │                            │ labels/
          │ rules/                     ▼
   ┌──────┴───────┐    PR     ┌──────────────────┐
   │ fraud-rules  │◀──────────│  fraud-reflector │
   │  + replay    │           │ (Claude tool_use)│
   └──────────────┘           └──────────────────┘
                                      ▲
                                      │ memory/
                                      │ attempts.jsonl
                                      │ rejections.jsonl
```

Every loop step has a corresponding skill and the wiring is real Python +
real GitHub: PRs open with `gh pr create`, CODEOWNERS gates the merge on a
human reviewer, rejected PRs feed back into `memory/rejections.jsonl` so the
reflector won't re-propose the same cluster for 14 days unless the evidence
doubles.

## Architecture (mapped to the HL paper)

| HL component       | This repo                                                  |
|--------------------|------------------------------------------------------------|
| Programmatic policy| `skills/fraud-rules/` — one named Python rule per scheme   |
| State representation| `skills/common/schemas.py` — `Transaction`, `EntityContext`|
| Feedback channels  | `labels/labels.jsonl` (analyst UI writes)                  |
| Experiment records | `runs/<date>.jsonl` (orchestrator writes)                  |
| Replays / tests    | `skills/fraud-replay/` — per-scheme recall floors          |
| Memory             | `memory/attempts.jsonl`, `memory/rejections.jsonl`         |
| Update mechanism   | `skills/fraud-reflector/` — Claude API + tool_use          |

## Quickstart

```bash
make install               # editable install, pulls dev deps
make test                  # 147 tests
make data                  # generate synthetic train/replay/holdout/stream splits
make ml-train              # train the baseline GBM (overwrites skills/fraud-ml/model.joblib)
make stream                # orchestrator: score the fixture, write runs/
make replay                # run all rules against the labeled fixture
make reflect               # offline reflector loop, materializes to proposals/
make results               # 14-day simulation → results/output/{headline.png, SUMMARY.md}
make ui                    # Streamlit analyst UI on http://localhost:8501
```

Live mode (hits Claude) needs `ANTHROPIC_API_KEY`:

```bash
ANTHROPIC_API_KEY=sk-... python -m reflector --live --open-pr
```

## Status against the 14-issue epic ([#1](../../issues/1))

- ✅ Closed: #2 data splits, #3 ML baseline, #4 schemas, #5 skill scaffolds,
  #6 seed rules, #7 replay harness, #8 analyst UI, #9 orchestrator,
  #10 reflector loop, #11 prompt design, #12 PR approval gate,
  #13 scheme injectors, #14 simulation/results, #15 overfitting guards
- 🟡 All 14 epic children closed.

The synthetic data generator (`data/build_splits.py`) emits IEEE-CIS-shape
splits — entity-level disjoint, deterministic from `RANDOM_SEED=42`. Replace
the generator with a real-IEEE-CIS loader (Kaggle download) and the rest of
the system runs unchanged.

## Headline simulation result

`make results` runs a 14-day timeline that injects three schemes the seed
rules miss by design:

| Scheme | Injected | First detected ≥ 80% recall | Time-to-detection |
|---|---:|---:|---:|
| new_bin_attack (BIN 654321, AT, online-cash-out) | day 3 | day 4 | < 1 simulated day |
| session_replay (shared device, 17s spacing, gaming) | day 5 | day 6 | < 1 simulated day |
| synthetic_id_ring (9 cards × 3 devices, NL luxury) | day 7 | day 8 | < 1 simulated day |

Seed-scheme recall stays flat at 1.0 across all 14 days — the anti-forgetting
guard works. Live-mode numbers (with a real Claude API call instead of the
deterministic stub proposer) land when CI gets an `ANTHROPIC_API_KEY`.

## Repo layout

```
skills/
  common/             # Transaction + EntityContext schemas
  fraud-ml/           # frozen ML scorer (stub for now; XGBoost lands in #3)
  fraud-rules/        # named Python rules + registry
  fraud-replay/       # labeled-corpus replay, per-scheme recall floors
  fraud-reflector/    # the HL update mechanism
    prompts/          # propose_rule.md (versioned)
    eval_clusters/    # hand-curated FN clusters for prompt eval
  orchestrator/       # runtime: ML + rules → decision → run log
  analyst-ui/         # Streamlit (labeling queue + PR review)
data/
  injectors/          # 3 synthetic fraud schemes (#13)
  replay/             # seed labeled fixture
  reflect/            # reflect-fixture builder
results/
  simulate.py         # 14-day timeline runner
  output/             # generated: timeline.jsonl, SUMMARY.md, headline.png
.github/
  CODEOWNERS                            # gates merge on rules/**
  PULL_REQUEST_TEMPLATE/reflector.md    # template for reflector PRs
  workflows/test.yml                    # pytest + replay on PR
runs/, labels/, memory/                  # gitignored; populated at runtime
```

## How to add a new rule

**By hand** — drop a file under `skills/fraud-rules/rules/`. Convention:
plain-English docstring, module-level `scheme_id` / `confidence` / `created_at` /
`author`, `applies(txn, ctx) -> bool`. Add tests under
`skills/fraud-rules/tests/`. `make replay` enforces no regression on existing
schemes; CI runs replay automatically on any PR touching rules.

**Via the reflector** — let it find the cluster, propose the rule, and open
a PR you review. The reflector ran offline by default — flip to live mode
when ready.

## Pointers

- The HL paper: https://trinkle23897.github.io/learning-beyond-gradients/
- Tracking epic: [#1](../../issues/1)
- POC plan in epic body (architecture + success metrics + run protocol)
