import json

from pr_template import parse_metadata, render_body


def _kwargs(**overrides) -> dict:
    base = dict(
        scheme_id="gift_card_micro_drain_v1",
        confidence=0.85,
        description="Test desc",
        rationale="Test rationale",
        cluster_id="cluster_AT_online-cash-out_new_newdev_mid",
        fn_count=7,
        cited_txn_ids=["t1", "t2", "t3", "t4", "t5"],
        created_at="2026-05-11",
    )
    base.update(overrides)
    return base


def test_render_includes_proposal_fields():
    body = render_body(**_kwargs())
    assert "gift_card_micro_drain_v1" in body
    assert "0.85" in body
    assert "Test desc" in body
    assert "cluster_AT_online-cash-out_new_newdev_mid" in body
    assert "`t1`" in body
    assert "2026-05-11" in body


def test_render_embeds_metadata_block():
    body = render_body(**_kwargs())
    metadata = parse_metadata(body)
    assert metadata["scheme_id"] == "gift_card_micro_drain_v1"
    assert metadata["cluster_id"] == "cluster_AT_online-cash-out_new_newdev_mid"
    assert metadata["fn_count"] == 7
    assert metadata["cited_txn_ids"] == ["t1", "t2", "t3", "t4", "t5"]


def test_parse_metadata_returns_none_when_missing():
    assert parse_metadata("just a regular PR body, no metadata") is None


def test_parse_metadata_returns_none_on_malformed_json():
    bad = """
    foo
    <!-- REFLECTOR_METADATA
    {not valid json}
    -->
    bar
    """
    assert parse_metadata(bad) is None


def test_render_handles_empty_cited_list():
    body = render_body(**_kwargs(cited_txn_ids=[]))
    assert "_(none)_" in body
