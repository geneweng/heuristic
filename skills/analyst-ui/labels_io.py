"""Append-only label store. One JSON record per line."""

import json
from datetime import datetime, timezone
from pathlib import Path


def load_labels(path: Path) -> dict[str, dict]:
    """Return {txn_id: most-recent-label-record}. Later writes win."""
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        out[rec["txn_id"]] = rec
    return out


def append_label(
    path: Path,
    *,
    txn_id: str,
    label: str,
    note: str = "",
    reviewer_id: str = "anonymous",
    now: datetime | None = None,
) -> dict:
    """Append a label record. label must be one of fraud/legit/unsure."""
    if label not in {"fraud", "legit", "unsure"}:
        raise ValueError(f"invalid label {label!r}")
    rec = {
        "txn_id": txn_id,
        "label": label,
        "note": note,
        "reviewer_id": reviewer_id,
        "labeled_at": (now or datetime.now(timezone.utc)).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec
