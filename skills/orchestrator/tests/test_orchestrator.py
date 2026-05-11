import json
import time
from datetime import datetime, timezone
from pathlib import Path

from orchestrator import run

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "data" / "replay" / "fixture.jsonl"


def _pinned_now():
    return datetime(2026, 5, 11, 14, 0, 0, tzinfo=timezone.utc)


def test_run_writes_one_record_per_txn(tmp_path):
    result = run(input_path=FIXTURE, runs_dir=tmp_path, now_factory=_pinned_now)
    log = tmp_path / "2026-05-11.jsonl"
    assert log.exists()
    lines = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    assert len(lines) == result["processed"]
    assert result["processed"] > 0


def test_run_log_records_match_schema(tmp_path):
    run(input_path=FIXTURE, runs_dir=tmp_path, now_factory=_pinned_now)
    line = json.loads((tmp_path / "2026-05-11.jsonl").read_text().splitlines()[0])
    assert {"ts", "txn", "ctx", "ml_prob", "fired_rules", "decision"} <= line.keys()
    assert line["decision"] in {"block", "review", "allow"}
    assert isinstance(line["fired_rules"], list)
    assert "txn_id" in line["txn"]


def test_run_is_deterministic_modulo_timestamps(tmp_path):
    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    run(input_path=FIXTURE, runs_dir=a_dir, now_factory=_pinned_now)
    run(input_path=FIXTURE, runs_dir=b_dir, now_factory=_pinned_now)
    a = [json.loads(line) for line in (a_dir / "2026-05-11.jsonl").read_text().splitlines()]
    b = [json.loads(line) for line in (b_dir / "2026-05-11.jsonl").read_text().splitlines()]
    # Strip the decision ts (it's the only field allowed to vary by definition).
    for rec in a + b:
        rec.pop("ts")
    assert a == b


def test_run_counts_decisions_in_response(tmp_path):
    result = run(input_path=FIXTURE, runs_dir=tmp_path, now_factory=_pinned_now)
    assert sum(result["counts"].values()) == result["processed"]
    # The seed fixture has 7 fraud cases; at least some should trigger non-allow decisions.
    assert result["counts"]["block"] + result["counts"]["review"] > 0


def test_run_throughput_above_100_per_sec(tmp_path):
    # Soft sanity check against the >=100 txn/sec AC. Replays the fixture 30x in memory.
    n = 30
    big = tmp_path / "big.jsonl"
    base = FIXTURE.read_text().strip().splitlines()
    big.write_text("\n".join(base * n) + "\n")
    start = time.perf_counter()
    result = run(input_path=big, runs_dir=tmp_path, now_factory=_pinned_now)
    elapsed = time.perf_counter() - start
    rate = result["processed"] / elapsed
    assert rate >= 100, f"throughput {rate:.0f} txn/s below floor"
