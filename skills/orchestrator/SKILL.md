---
name: orchestrator
description: Runtime path that scores each txn with ML + rules, makes a decision, and writes the run log
---

# orchestrator

The runtime path that processes each transaction from the stream. Composes `fraud-ml`
and `fraud-rules`, picks block/review/allow, and appends one record per txn to
`runs/<date>.jsonl`. That log is what the reflector reads to find what was missed.

## Usage

```bash
make stream                  # uses data/replay/fixture.jsonl by default
make stream INPUT=data/...   # override input path
```

## Output

See `runs/SCHEMA.md` for the run-log record format.

## Decision policy

Thresholds are fixed (deterministic, no random):

- **block**  — `max(ml_prob, max rule confidence) > 0.9`
- **review** — same > 0.5
- **allow**  — otherwise
