"""FNCluster — the unit of input to the reflector's `propose_rule` prompt.

A cluster is a group of false-negative transactions that look similar by feature.
Each cluster is built (in #10) by the reflector from `runs/` + `labels/`, but for
the prompt-design work we load them from `eval_clusters/*.json` to evaluate the
prompt deterministically.

Validators here are the *first gate* before the LLM ever sees a cluster — they
reject obvious noise (too small, one card, one merchant) cheaply, before paying
for an API call.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

MIN_FN_RECORDS = 5


@dataclass(frozen=True)
class FNRecord:
    """A single false-negative txn + the context the rules saw + analyst note."""

    txn_id: str
    txn: dict          # Transaction fields (snake-case dict, ready for the prompt)
    ctx: dict          # EntityContext fields at decision time
    analyst_note: str = ""


@dataclass(frozen=True)
class FNCluster:
    cluster_id: str
    fn_records: tuple[FNRecord, ...]
    analyst_summary: str = ""
    expected_scheme_name: str | None = None  # for eval comparison; None in live ops
    metadata: dict = field(default_factory=dict)


# --- loading ------------------------------------------------------------------


def load_cluster(path: Path) -> FNCluster:
    raw = json.loads(Path(path).read_text())
    return FNCluster(
        cluster_id=raw["cluster_id"],
        fn_records=tuple(FNRecord(**r) for r in raw["fn_records"]),
        analyst_summary=raw.get("analyst_summary", ""),
        expected_scheme_name=raw.get("expected_scheme_name"),
        metadata=raw.get("metadata", {}),
    )


def load_all_clusters(dir_path: Path) -> list[FNCluster]:
    return sorted(
        (load_cluster(p) for p in sorted(Path(dir_path).glob("*.json"))),
        key=lambda c: c.cluster_id,
    )


# --- validators ---------------------------------------------------------------


def validate_cluster(cluster: FNCluster) -> list[str]:
    """Pre-prompt validation. Returns a list of issues; empty = ready for the LLM.

    Keep these checks cheap and obvious — they catch the noise that would cause
    a hallucinated rule, before the API call is made.
    """
    issues: list[str] = []

    n = len(cluster.fn_records)
    if n < MIN_FN_RECORDS:
        issues.append(f"too few FNs ({n}, need >= {MIN_FN_RECORDS})")

    if n == 0:
        return issues  # the rest of the checks would crash on empty

    def _uniq(key: str) -> set:
        return {r.txn.get(key) for r in cluster.fn_records}

    cards = _uniq("card_id")
    if len(cards) == 1:
        issues.append(f"all FNs share card_id={next(iter(cards))} — single customer, not a scheme")

    merchants = _uniq("merchant_id")
    if len(merchants) == 1 and n >= 3:
        issues.append(
            f"all FNs share merchant_id={next(iter(merchants))} — likely merchant-specific noise"
        )

    devices = _uniq("device_id")
    if len(devices) == 1 and len(cards) == 1:
        issues.append("all FNs share one (card, device) pair — not a generalizable pattern")

    return issues


def is_valid(cluster: FNCluster) -> bool:
    return not validate_cluster(cluster)
