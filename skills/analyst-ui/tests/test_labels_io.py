import json
from datetime import datetime, timezone

import pytest

from labels_io import append_label, load_labels


def test_load_returns_empty_dict_when_file_missing(tmp_path):
    assert load_labels(tmp_path / "nope.jsonl") == {}


def test_append_and_round_trip(tmp_path):
    path = tmp_path / "labels.jsonl"
    rec = append_label(
        path,
        txn_id="t1",
        label="fraud",
        note="suspicious",
        reviewer_id="alice",
        now=datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert rec["txn_id"] == "t1"
    loaded = load_labels(path)
    assert loaded["t1"]["label"] == "fraud"
    assert loaded["t1"]["reviewer_id"] == "alice"


def test_invalid_label_rejected(tmp_path):
    with pytest.raises(ValueError):
        append_label(tmp_path / "x.jsonl", txn_id="t", label="maybe")


def test_later_write_wins_for_same_txn(tmp_path):
    path = tmp_path / "labels.jsonl"
    append_label(path, txn_id="t", label="legit", reviewer_id="alice")
    append_label(path, txn_id="t", label="fraud", reviewer_id="bob")
    loaded = load_labels(path)
    assert loaded["t"]["label"] == "fraud"
    assert loaded["t"]["reviewer_id"] == "bob"


def test_append_creates_parent_dir(tmp_path):
    path = tmp_path / "nested" / "more" / "labels.jsonl"
    append_label(path, txn_id="t", label="legit")
    assert path.exists()
