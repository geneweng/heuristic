---
name: fraud-ml
description: Frozen GBM scorer for fraud probability + top contributing features
---

# fraud-ml

The ML half of the detection stack. **Frozen** for the duration of the POC —
the HL thesis is that rules adapt while ML stays still, so any new detection
is attributable to the reflector loop, not retraining.

## Inputs / outputs

```python
from fraud_ml import score
out = score(txn, ctx)
# {"prob": float, "top_features": list[str]}
```

## Artifact

- `model.joblib`            — checked-in trained model (~250 KB)
- `BASELINE.md`             — auto-generated; holdout metrics
- `features.py`             — feature engineering shared by train + score
- `train.py`                — entry point; reads `data/splits/` and writes the artifact

## Retraining

```bash
make data        # regenerate splits (deterministic, seed=42)
make ml-train    # fit, evaluate, write artifact + BASELINE.md
```

The model is the GBM trained on `data/splits/train.parquet`; never retrained at
runtime. If `model.joblib` is missing, `score()` falls back to `prob=0.0` so
the rest of the pipeline still runs (preserves the stub behavior callers had
before #3).

## Algorithm choice

`sklearn.ensemble.HistGradientBoostingClassifier` instead of XGBoost. XGBoost
needs `libomp` on macOS which isn't always installed; HistGBM is sklearn-native
and matches XGBoost's perf on synthetic data. One-line swap if a project
mandates XGBoost.
