"""Build the labeling queue: flagged txns from runs/ that don't have a label yet."""

import json
from pathlib import Path

from labels_io import load_labels

FLAG_DECISIONS = {"review", "block"}


def _load_runs(runs_dir: Path) -> list[dict]:
    out: list[dict] = []
    for f in sorted(runs_dir.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def build_queue(runs_dir: Path, labels_path: Path) -> list[dict]:
    """Return flagged unlabeled txns, newest decision first.

    Each entry is the run-log record verbatim. The Streamlit page renders it.
    """
    labels = load_labels(labels_path)
    runs = _load_runs(runs_dir)
    queue = [
        r for r in runs
        if r.get("decision") in FLAG_DECISIONS
        and r.get("txn", {}).get("txn_id") not in labels
    ]
    queue.sort(key=lambda r: r.get("ts", ""), reverse=True)
    return queue
