from tool_schema import DECLINE_TOOL, PROPOSE_RULE_TOOL, REFLECTOR_TOOLS


def test_propose_rule_required_fields():
    required = set(PROPOSE_RULE_TOOL["input_schema"]["required"])
    assert {
        "scheme_id",
        "description",
        "rationale",
        "predicate_code",
        "positive_tests",
        "negative_tests",
        "cited_txn_ids",
        "confidence",
    } <= required


def test_scheme_id_pattern_enforces_versioned_slug():
    pattern = PROPOSE_RULE_TOOL["input_schema"]["properties"]["scheme_id"]["pattern"]
    import re

    ok = ["gift_card_micro_drain_v1", "x_v2", "abc_def_v99"]
    bad = ["Rule47", "scheme-with-dashes", "no_version", "_leading_underscore_v1"]
    for s in ok:
        assert re.match(pattern, s), f"{s} should match"
    for s in bad:
        assert not re.match(pattern, s), f"{s} should NOT match"


def test_positive_and_negative_test_arrays_require_min_3():
    pos = PROPOSE_RULE_TOOL["input_schema"]["properties"]["positive_tests"]
    neg = PROPOSE_RULE_TOOL["input_schema"]["properties"]["negative_tests"]
    assert pos["minItems"] == 3
    assert neg["minItems"] == 3


def test_cited_txn_ids_requires_min_5():
    cited = PROPOSE_RULE_TOOL["input_schema"]["properties"]["cited_txn_ids"]
    assert cited["minItems"] == 5


def test_decline_tool_requires_reason():
    assert "reason" in DECLINE_TOOL["input_schema"]["required"]


def test_reflector_tools_contains_both():
    names = {t["name"] for t in REFLECTOR_TOOLS}
    assert names == {"propose_rule", "decline_rule_proposal"}
