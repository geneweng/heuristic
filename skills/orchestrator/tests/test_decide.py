from orchestrator import decide


def test_block_on_high_ml():
    d = decide(ml_prob=0.95, fired_rules=[])
    assert d.decision == "block"


def test_block_on_high_rule_confidence():
    d = decide(ml_prob=0.0, fired_rules=[("X", 0.92)])
    assert d.decision == "block"


def test_review_on_medium_ml():
    d = decide(ml_prob=0.7, fired_rules=[])
    assert d.decision == "review"


def test_review_on_medium_rule():
    d = decide(ml_prob=0.0, fired_rules=[("X", 0.6)])
    assert d.decision == "review"


def test_allow_when_all_signals_low():
    d = decide(ml_prob=0.1, fired_rules=[("X", 0.3)])
    assert d.decision == "allow"


def test_block_threshold_is_strict():
    # Exactly 0.9 should NOT block (strictly greater).
    assert decide(ml_prob=0.9, fired_rules=[]).decision == "review"


def test_max_signal_drives_decision():
    # One high-confidence rule beats many low ones.
    d = decide(ml_prob=0.0, fired_rules=[("a", 0.1), ("b", 0.2), ("c", 0.95)])
    assert d.decision == "block"
