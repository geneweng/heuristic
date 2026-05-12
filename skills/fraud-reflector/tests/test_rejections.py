from datetime import datetime, timedelta, timezone

from rejections import append_rejection, load_rejections, should_skip_cluster


def _rej(cluster_id: str, *, fn_count: int, days_ago: int, scheme_id: str = "s_v1") -> dict:
    return {
        "cluster_id": cluster_id,
        "scheme_id": scheme_id,
        "fn_count": fn_count,
        "reason": "x",
        "rejected_at": (datetime(2026, 5, 11, tzinfo=timezone.utc) - timedelta(days=days_ago)).isoformat(),
    }


_NOW = datetime(2026, 5, 11, tzinfo=timezone.utc)


def test_no_rejection_does_not_skip():
    skip, _ = should_skip_cluster("c1", 10, rejections=[], now=_NOW)
    assert skip is False


def test_recent_rejection_with_no_new_evidence_skips():
    rejections = [_rej("c1", fn_count=7, days_ago=3)]
    skip, reason = should_skip_cluster("c1", 7, rejections, now=_NOW)
    assert skip is True
    assert "rejected 3d ago" in reason


def test_old_rejection_does_not_skip():
    rejections = [_rej("c1", fn_count=7, days_ago=20)]
    skip, _ = should_skip_cluster("c1", 7, rejections, now=_NOW)
    assert skip is False


def test_recent_rejection_with_doubled_evidence_does_not_skip():
    rejections = [_rej("c1", fn_count=7, days_ago=3)]
    skip, _ = should_skip_cluster("c1", 14, rejections, now=_NOW)
    assert skip is False


def test_recent_rejection_with_below_double_evidence_skips():
    rejections = [_rej("c1", fn_count=7, days_ago=3)]
    skip, _ = should_skip_cluster("c1", 13, rejections, now=_NOW)
    assert skip is True


def test_latest_rejection_is_authoritative():
    # An older rejection had high fn_count; a newer one is what counts.
    rejections = [
        _rej("c1", fn_count=20, days_ago=10),
        _rej("c1", fn_count=5, days_ago=2),
    ]
    skip, _ = should_skip_cluster("c1", 9, rejections, now=_NOW)
    assert skip is True  # latest required 10; we have 9
    skip, _ = should_skip_cluster("c1", 10, rejections, now=_NOW)
    assert skip is False  # latest required 10; we have 10


def test_rejections_for_different_clusters_dont_collide():
    rejections = [_rej("c_other", fn_count=7, days_ago=3)]
    skip, _ = should_skip_cluster("c_mine", 7, rejections, now=_NOW)
    assert skip is False


def test_append_and_load_round_trip(tmp_path):
    path = tmp_path / "rejections.jsonl"
    append_rejection(cluster_id="c1", scheme_id="s_v1", fn_count=7, reason="r1", path=path, now=_NOW)
    append_rejection(cluster_id="c2", scheme_id="s_v2", fn_count=5, reason="r2", path=path, now=_NOW)
    recs = load_rejections(path)
    assert {r["cluster_id"] for r in recs} == {"c1", "c2"}
    assert recs[0]["scheme_id"] == "s_v1"
