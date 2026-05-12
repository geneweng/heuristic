"""Rejection memory — the reflector reads this before proposing a new rule.

When an analyst rejects a reflector-opened PR, the rejection lands here. On
the next run the reflector checks the file and skips any cluster whose
fingerprint matches a recent rejection — unless the evidence count has
doubled, which signals the pattern is now strong enough to revisit.

Rationale (#12 AC): "Rejections feed back into the next reflector run (don't
re-propose for ≥ 14 days unless evidence count doubles)."
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REJECTIONS_LOG = REPO_ROOT / "memory" / "rejections.jsonl"

DEFAULT_TTL_DAYS = 14
DEFAULT_EVIDENCE_MULTIPLE = 2


def append_rejection(
    *,
    cluster_id: str,
    scheme_id: str,
    fn_count: int,
    reason: str,
    path: Path = DEFAULT_REJECTIONS_LOG,
    now: datetime | None = None,
) -> dict:
    """Append a single rejection record. Returns the record written."""
    rec = {
        "cluster_id": cluster_id,
        "scheme_id": scheme_id,
        "fn_count": fn_count,
        "reason": reason,
        "rejected_at": (now or datetime.now(timezone.utc)).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def load_rejections(path: Path = DEFAULT_REJECTIONS_LOG) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def should_skip_cluster(
    cluster_id: str,
    current_fn_count: int,
    rejections: list[dict],
    *,
    now: datetime | None = None,
    ttl_days: int = DEFAULT_TTL_DAYS,
    evidence_multiple: int = DEFAULT_EVIDENCE_MULTIPLE,
) -> tuple[bool, str]:
    """Decide whether to skip a cluster given prior rejections.

    Returns (skip, reason). reason is "" when skip=False.
    """
    matching = [r for r in rejections if r.get("cluster_id") == cluster_id]
    if not matching:
        return False, ""

    matching.sort(key=lambda r: r["rejected_at"], reverse=True)
    latest = matching[0]
    rejected_at = datetime.fromisoformat(latest["rejected_at"])
    age = (now or datetime.now(timezone.utc)) - rejected_at
    if age > timedelta(days=ttl_days):
        return False, ""

    rejected_count = int(latest.get("fn_count", 0) or 0)
    if rejected_count and current_fn_count >= rejected_count * evidence_multiple:
        return False, ""

    return True, (
        f"cluster {cluster_id!r} rejected {age.days}d ago "
        f"(fn_count then={rejected_count}, now={current_fn_count}); "
        f"need >= {rejected_count * evidence_multiple} or {ttl_days}d wait"
    )
