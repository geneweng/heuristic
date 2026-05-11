---
name: fraud-rules
description: Registry of programmatic fraud rules; each rule names one scheme
---

# fraud-rules

The HL paper's "programmatic policy." Every file under `rules/` defines one rule for one
named scheme. The registry auto-discovers them at import time.

## Rule contract

Each rule file must expose module-level attributes:

- `scheme_id: str` — slug naming the scheme (e.g. `card_testing_burst_v2`)
- `confidence: float` — 0..1, how strong a signal a fire is
- `created_at: str` — ISO date
- `author: str` — `human:<name>` or `reflector:<run_id>`
- `applies(txn, ctx) -> bool` — the predicate

## Usage

```python
from registry import evaluate
fired = evaluate(txn, ctx)  # [(scheme_id, confidence), ...]
```

## Status

Registry implemented; `rules/` is empty until issue #6 seeds it.
