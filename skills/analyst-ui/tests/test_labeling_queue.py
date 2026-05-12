import json
from pathlib import Path

from labels_io import append_label
from labeling_queue import build_queue


def _run(txn_id: str, decision: str, ts: str = "2026-05-11T12:00:00") -> dict:
    return {
        "ts": ts,
        "txn": {"txn_id": txn_id, "amount": "10.00"},
        "ctx": {},
        "ml_prob": 0.0,
        "fired_rules": [],
        "decision": decision,
    }


def _write_runs(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def test_includes_review_and_block_only(tmp_path):
    runs = tmp_path / "runs"
    _write_runs(runs / "d.jsonl", [
        _run("t_allow", "allow"),
        _run("t_block", "block"),
        _run("t_review", "review"),
    ])
    q = build_queue(runs, tmp_path / "labels.jsonl")
    ids = {r["txn"]["txn_id"] for r in q}
    assert ids == {"t_block", "t_review"}


def test_excludes_already_labeled(tmp_path):
    runs = tmp_path / "runs"
    labels = tmp_path / "labels.jsonl"
    _write_runs(runs / "d.jsonl", [_run("t1", "review"), _run("t2", "review")])
    append_label(labels, txn_id="t1", label="fraud")
    q = build_queue(runs, labels)
    assert [r["txn"]["txn_id"] for r in q] == ["t2"]


def test_orders_newest_first(tmp_path):
    runs = tmp_path / "runs"
    _write_runs(runs / "d.jsonl", [
        _run("old", "review", ts="2026-05-01T12:00:00"),
        _run("new", "review", ts="2026-05-11T12:00:00"),
        _run("mid", "review", ts="2026-05-06T12:00:00"),
    ])
    q = build_queue(runs, tmp_path / "labels.jsonl")
    assert [r["txn"]["txn_id"] for r in q] == ["new", "mid", "old"]


def test_empty_runs_dir_yields_empty_queue(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    assert build_queue(runs, tmp_path / "labels.jsonl") == []
