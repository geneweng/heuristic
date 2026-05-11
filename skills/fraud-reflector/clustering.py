"""Feature-bucket clustering for false-negative records.

Deviation from the issue's "simple kmeans" suggestion: bucketing by interpretable
feature keys is deterministic, sklearn-free, and matches the HL paper's
interpretability story — an analyst can read a cluster key and know what the
cluster represents. With POC-sized FN volumes this is plenty; swap for kmeans
if/when feature spaces grow beyond what discrete bucketing can handle.
"""

from collections import defaultdict
from decimal import Decimal

from clusters import FNCluster, FNRecord


DEFAULT_MIN_CLUSTER_SIZE = 5


def _age_bucket(days: int | None) -> str:
    if days is None:
        return "unknown"
    if days < 30:
        return "new"
    if days < 90:
        return "young"
    if days < 365:
        return "established"
    return "aged"


def _amount_bucket(amount_str: str | None) -> str:
    try:
        a = Decimal(str(amount_str))
    except Exception:
        return "unknown"
    if a < Decimal("5"):
        return "micro"
    if a < Decimal("50"):
        return "low"
    if a < Decimal("500"):
        return "mid"
    return "high"


def _features(rec: FNRecord) -> tuple[str, ...]:
    txn = rec.txn
    ctx = rec.ctx
    return (
        str(txn.get("country", "")),
        str(txn.get("merchant_category", "")),
        _age_bucket(ctx.get("card_age_days")),
        "newdev" if not ctx.get("current_device_seen_before_for_card", True) else "knowndev",
        _amount_bucket(txn.get("amount")),
    )


def cluster_fns(
    fns: list[FNRecord], *, min_size: int = DEFAULT_MIN_CLUSTER_SIZE
) -> list[FNCluster]:
    """Group FNs by feature bucket; drop buckets smaller than min_size."""
    buckets: dict[tuple[str, ...], list[FNRecord]] = defaultdict(list)
    for fn in fns:
        buckets[_features(fn)].append(fn)

    clusters: list[FNCluster] = []
    for key, recs in sorted(buckets.items()):
        if len(recs) < min_size:
            continue
        clusters.append(
            FNCluster(
                cluster_id="cluster_" + "_".join(k.replace(" ", "-") or "x" for k in key),
                fn_records=tuple(recs),
                analyst_summary=(
                    f"FNs sharing country={key[0]}, merchant_category={key[1]}, "
                    f"card_age={key[2]}, device={key[3]}, amount={key[4]}"
                ),
            )
        )
    return clusters
