from metrics import (
    CombinedMetrics,
    ScoredRecord,
    _pr_auc,
    compute_combined_metrics,
    compute_scheme_metrics,
)


def _r(true: str | None, fired: list[tuple[str, float]], is_fraud: bool = True, ml: float = 0.0):
    return ScoredRecord(true_scheme_id=true, is_fraud=is_fraud, ml_prob=ml, fired_rules=tuple(fired))


def test_scheme_metrics_basic_tp_fp_fn():
    records = [
        _r("A", [("A", 0.9)]),                       # TP for A
        _r("A", []),                                 # FN for A
        _r(None, [("A", 0.9)], is_fraud=False),      # FP for A
        _r("B", [("B", 0.8)]),                       # unrelated
    ]
    m = compute_scheme_metrics(records, ["A", "B"])
    assert (m["A"].tp, m["A"].fp, m["A"].fn) == (1, 1, 1)
    assert m["A"].precision == 0.5
    assert m["A"].recall == 0.5


def test_scheme_metrics_no_fires_yields_zero_precision():
    records = [_r("A", [])]
    m = compute_scheme_metrics(records, ["A"])
    assert m["A"].precision == 0.0
    assert m["A"].recall == 0.0


def test_combined_recall_counts_any_rule_fire_or_high_ml():
    records = [
        _r("A", [("A", 0.9)], is_fraud=True),        # flagged via rule
        _r("B", [], is_fraud=True, ml=0.8),          # flagged via ML
        _r("C", [], is_fraud=True, ml=0.1),          # missed
        _r(None, [], is_fraud=False),                # true negative
    ]
    c = compute_combined_metrics(records, flag_threshold=0.5)
    assert c.flagged_recall == 2 / 3
    assert c.flagged_precision == 1.0


def test_pr_auc_perfect_ranking_is_one():
    scores = [0.9, 0.8, 0.2, 0.1]
    labels = [True, True, False, False]
    assert _pr_auc(scores, labels) == 1.0


def test_pr_auc_with_no_positives_is_zero():
    assert _pr_auc([0.5, 0.4], [False, False]) == 0.0


def test_pr_auc_handles_ties_at_top():
    # Two positives tied at the top with one negative — AP should still be 1.0
    # because both positives are recovered before any negative.
    scores = [0.9, 0.9, 0.1]
    labels = [True, True, False]
    assert _pr_auc(scores, labels) == 1.0


def test_combined_metrics_returns_dataclass():
    c = compute_combined_metrics([], flag_threshold=0.5)
    assert isinstance(c, CombinedMetrics)
    assert c.flagged_recall == 0.0
