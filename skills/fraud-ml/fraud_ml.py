"""fraud-ml — frozen GBM scorer.

Loads the model artifact once on first call and reuses it. Returns a fraud
probability plus the top-K feature names that contributed most to this txn
(by raw-feature magnitude, not SHAP — POC-grade attribution).

If the model artifact is missing, falls back to `prob=0.0` so the system
still runs in stub mode (preserving the bootstrap behavior callers expected
before #3 landed).
"""

from __future__ import annotations

import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np

from features import FEATURE_NAMES, featurize_one
from schemas import EntityContext, Transaction

# Suppress the per-call sklearn warning about predict_proba being passed a raw
# ndarray rather than a column-named DataFrame. Wrapping in a DataFrame would
# add measurable overhead in the orchestrator hot path; the warning is benign.
warnings.filterwarnings("ignore", message=".*does not have valid feature names.*")

MODEL_PATH = Path(__file__).parent / "model.joblib"
TOP_K_FEATURES = 5


@lru_cache(maxsize=1)
def _load() -> tuple[object, list[str]] | None:
    if not MODEL_PATH.exists():
        return None
    import joblib

    payload = joblib.load(MODEL_PATH)
    return payload["model"], payload["feature_names"]


def score(txn: Transaction, ctx: EntityContext) -> dict:
    loaded = _load()
    if loaded is None:
        return {"prob": 0.0, "top_features": []}
    model, feature_names = loaded

    x = featurize_one(txn, ctx).reshape(1, -1)
    prob = float(model.predict_proba(x)[0, 1])

    # Cheap per-row "importance": features with largest magnitude in this txn.
    abs_vals = np.abs(x[0])
    top_idx = np.argsort(-abs_vals)[:TOP_K_FEATURES]
    top_features = [feature_names[i] for i in top_idx]
    return {"prob": prob, "top_features": top_features}
