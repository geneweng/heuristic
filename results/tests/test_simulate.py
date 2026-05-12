import json
from pathlib import Path

from simulate import simulate


def test_simulate_writes_timeline_and_summary(tmp_path):
    out = tmp_path / "sim"
    summary = simulate(output_dir=out)

    assert summary["days"] == 14
    timeline_path = out / "timeline.jsonl"
    summary_path = out / "SUMMARY.md"
    assert timeline_path.exists()
    assert summary_path.exists()

    lines = timeline_path.read_text().strip().splitlines()
    assert len(lines) == 14
    last = json.loads(lines[-1])
    assert "scheme_recall" in last


def test_simulate_eventually_catches_at_least_one_scheme(tmp_path):
    """With the stub proposer + offline rules, at least one scheme should be
    fully caught by the end of the timeline. (Bar is intentionally weak; the
    real-quality measurement waits for live-mode + #2 holdout data.)"""
    out = tmp_path / "sim"
    summary = simulate(output_dir=out)
    final = summary["final_recall"]
    caught = [sid for sid, r in final.items() if r >= 0.5]
    assert caught, f"no scheme reached 50% recall; finals={final}"


def test_summary_lists_all_three_schemes(tmp_path):
    out = tmp_path / "sim"
    simulate(output_dir=out)
    md = (out / "SUMMARY.md").read_text()
    for scheme in ("A:", "B:", "C:"):
        assert scheme in md
