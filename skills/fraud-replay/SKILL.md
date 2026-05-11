---
name: fraud-replay
description: Run current rules + ML against the labeled replay set; enforce per-scheme recall floors
---

# fraud-replay

The anti-forgetting guard. Loads the replay split, runs `fraud-ml` + `fraud-rules` against
every transaction, emits per-scheme precision/recall, and exits non-zero if any prior
scheme's recall falls below the floor in `floors.yaml`.

## Usage

```bash
make replay
```

Outputs:
- `replay_report.json` — machine-readable
- `replay_report.md` — human-readable summary

## Status

Stub. Implementation lands in issue #7.
