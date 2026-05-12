import json
from dataclasses import dataclass

from pr_review import (
    ReflectorPR,
    approve_pr,
    get_pr_diff,
    list_open_reflector_prs,
    reject_pr,
)


@dataclass
class FakeResult:
    stdout: str = ""


def _runner(stdout: str = ""):
    """Return a callable that mimics subprocess.run and records args."""
    calls = []

    def runner(args, check=True, capture_output=True, text=True):
        calls.append(args)
        return FakeResult(stdout=stdout)

    runner.calls = calls
    return runner


def test_list_filters_to_reflector_titled_prs():
    payload = json.dumps([
        {"number": 1, "title": "reflector: gift_card_v1", "body": "x", "headRefName": "reflector/gift_card_v1", "url": "u1"},
        {"number": 2, "title": "fix typo", "body": "y", "headRefName": "fix-typo", "url": "u2"},
        {"number": 3, "title": "reflector: refund_v1", "body": "z", "headRefName": "reflector/refund_v1", "url": "u3"},
    ])
    runner = _runner(stdout=payload)
    prs = list_open_reflector_prs(runner=runner)

    assert [p.number for p in prs] == [1, 3]
    assert isinstance(prs[0], ReflectorPR)
    assert runner.calls[0][:3] == ["gh", "pr", "list"]


def test_get_pr_diff_invokes_pr_diff_with_number():
    runner = _runner(stdout="diff content here")
    out = get_pr_diff(42, runner=runner)
    assert out == "diff content here"
    assert runner.calls == [["gh", "pr", "diff", "42"]]


def test_approve_uses_squash():
    runner = _runner(stdout="merged")
    approve_pr(7, runner=runner)
    assert runner.calls == [["gh", "pr", "merge", "7", "--squash"]]


def test_reject_comments_then_closes():
    runner = _runner(stdout="")
    reject_pr(9, "not generalizable", runner=runner)
    assert runner.calls == [
        ["gh", "pr", "comment", "9", "--body", "not generalizable"],
        ["gh", "pr", "close", "9"],
    ]


def test_reject_reflector_pr_records_rejection_when_metadata_present(tmp_path):
    from pr_review import reject_reflector_pr

    body = """### Reflector PR

<!-- REFLECTOR_METADATA
{"scheme_id": "promo_v1", "cluster_id": "cluster_promo", "fn_count": 8, "cited_txn_ids": ["a","b"]}
-->
"""
    pr = ReflectorPR(number=11, title="reflector: promo_v1", body=body, head_ref="r/promo", url="u")
    runner = _runner(stdout="")
    rejections_path = tmp_path / "rejections.jsonl"

    rec = reject_reflector_pr(pr, "too narrow", rejections_path=rejections_path, runner=runner)

    assert rec["cluster_id"] == "cluster_promo"
    assert rec["fn_count"] == 8
    assert rec["reason"] == "too narrow"
    assert rejections_path.exists()
    # gh calls still ran in the expected order
    assert runner.calls == [
        ["gh", "pr", "comment", "11", "--body", "too narrow"],
        ["gh", "pr", "close", "11"],
    ]


def test_reject_reflector_pr_with_no_metadata_still_closes(tmp_path):
    from pr_review import reject_reflector_pr

    pr = ReflectorPR(number=12, title="reflector: x", body="no metadata here", head_ref="r/x", url="u")
    runner = _runner(stdout="")
    rejections_path = tmp_path / "rejections.jsonl"

    rec = reject_reflector_pr(pr, "stale", rejections_path=rejections_path, runner=runner)
    assert rec == {}
    assert not rejections_path.exists()
    assert runner.calls[0][1:3] == ["pr", "comment"]
    assert runner.calls[1][1:3] == ["pr", "close"]
