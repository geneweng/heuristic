from datetime import date

from materialize import materialize_rule


def _proposal(**overrides) -> dict:
    base = {
        "scheme_id": "test_pattern_v1",
        "description": "Test pattern catching X when Y is high and Z is true.",
        "rationale": "structural",
        "predicate_code": "return ctx.card_age_days > 90 and txn.amount > Decimal('500')",
        "confidence": 0.85,
        "cited_txn_ids": ["a", "b", "c", "d", "e"],
        "positive_tests": [
            {"txn_overrides": {"amount": "700"}, "ctx_overrides": {"card_age_days": 200}, "expected_fire": True},
            {"txn_overrides": {"amount": "800"}, "ctx_overrides": {"card_age_days": 120}, "expected_fire": True},
            {"txn_overrides": {"amount": "501"}, "ctx_overrides": {"card_age_days": 91}, "expected_fire": True},
        ],
        "negative_tests": [
            {"txn_overrides": {"amount": "10"}, "ctx_overrides": {"card_age_days": 200}, "expected_fire": False},
            {"txn_overrides": {"amount": "700"}, "ctx_overrides": {"card_age_days": 30}, "expected_fire": False},
            {"txn_overrides": {"amount": "500"}, "ctx_overrides": {"card_age_days": 200}, "expected_fire": False},
        ],
    }
    base.update(overrides)
    return base


def test_materialize_writes_rule_and_test_file(tmp_path):
    rules_dir = tmp_path / "rules"
    tests_dir = tmp_path / "tests"
    rule_p, test_p = materialize_rule(_proposal(), rules_dir, tests_dir, today=date(2026, 5, 11))

    assert rule_p.exists() and test_p.exists()
    rule_src = rule_p.read_text()
    assert 'scheme_id = "test_pattern_v1"' in rule_src
    assert "Test pattern catching X" in rule_src
    assert "card_age_days > 90" in rule_src
    assert 'created_at = "2026-05-11"' in rule_src
    assert 'author = "reflector"' in rule_src


def test_materialized_test_file_contains_3_pos_3_neg(tmp_path):
    rule_p, test_p = materialize_rule(
        _proposal(), tmp_path / "rules", tmp_path / "tests", today=date(2026, 5, 11)
    )
    src = test_p.read_text()
    assert src.count("def test_positive_") == 3
    assert src.count("def test_negative_") == 3
    assert "from rules.test_pattern_v1 import applies" in src


def test_materialize_produces_runnable_python(tmp_path):
    """The generated rule must parse and load — confirms our templating is sound."""
    import sys

    rule_p, test_p = materialize_rule(
        _proposal(), tmp_path / "rules", tmp_path / "tests", today=date(2026, 5, 11)
    )

    # Compile both files to catch templating bugs.
    compile(rule_p.read_text(), str(rule_p), "exec")
    compile(test_p.read_text(), str(test_p), "exec")
