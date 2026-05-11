---
name: fraud-ml
description: Score a transaction with a frozen gradient-boosted fraud classifier
---

# fraud-ml

The ML half of the detection stack. **Frozen for the duration of the POC** — the HL thesis
is that rules adapt while ML stays still, so we can attribute any new detections to the
reflector loop.

## Inputs

`Transaction` + `EntityContext` (see `skills/common/schemas.py`).

## Outputs

```python
{"prob": float, "top_features": list[str]}
```

## Status

Stub. Returns `prob=0.0` until issue #3 lands the trained XGBoost model.
