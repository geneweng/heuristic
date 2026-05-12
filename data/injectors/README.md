# Synthetic fraud-scheme injectors

Three schemes the frozen ML and seed rules miss by design — used for the #14
end-to-end demo. Each generator returns `(run_record, label_record)` tuples
in the same shape `data/reflect/build_fixture.py` emits, so the reflector
loop consumes them without changes.

## Schemes

| Module | Scheme | Signal | Why ML misses it |
|---|---|---|---|
| `new_bin_attack.py` | BIN abuse | `bin=654321`, country=AT, merchant_category=online-cash-out, $199 | BIN issued after training cutoff |
| `session_replay.py` | Replay harness | Same device + IP, 17s jitter, gaming, ~$47 | "Inter-arrival regularity" not in ML features |
| `synthetic_id_ring.py` | Bust-out ring | 9 cards × 3 devices, NL, luxury, $400–600 | No card individually looks worse than threshold |

## Acceptance gating

Per #13 AC: every scheme is verified to be missed by the frozen ML (which is
stubbed at `prob=0.0` in the POC, so trivially true). Synthetic txns ship
with `label="fraud"` so the analyst-UI simulation can skip manual review.

## Usage

```bash
python -m inject --schemes new_bin_attack,session_replay --start-day 3 \
    --runs runs/sim.jsonl --labels labels/sim_labels.jsonl
```

The simulation script under `results/simulate.py` composes all three.
