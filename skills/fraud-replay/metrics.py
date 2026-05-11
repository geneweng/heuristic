"""Per-scheme + combined metrics for the replay harness.

A `ScoredRecord` is the unit of replay evaluation:
- `true_scheme_id`: the scheme that produced the txn, or None for legit traffic
- `is_fraud`: whether the txn is fraudulent at all (covers schemes outside our rule set)
- `ml_prob`: ML score
- `fired_rules`: list of (scheme_id, confidence) tuples that fired on this txn
"""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ScoredRecord:
    true_scheme_id: str | None
    is_fraud: bool
    ml_prob: float
    fired_rules: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class SchemeMetrics:
    scheme_id: str
    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 0.0


def compute_scheme_metrics(
    records: Iterable[ScoredRecord], scheme_ids: Iterable[str]
) -> dict[str, SchemeMetrics]:
    """For each rule's scheme_id, count TP/FP/FN against the true_scheme_id labels."""
    out: dict[str, SchemeMetrics] = {}
    records = list(records)
    for sid in scheme_ids:
        tp = fp = fn = 0
        for r in records:
            fired = any(s == sid for s, _ in r.fired_rules)
            target = r.true_scheme_id == sid
            if fired and target:
                tp += 1
            elif fired and not target:
                fp += 1
            elif not fired and target:
                fn += 1
        out[sid] = SchemeMetrics(scheme_id=sid, tp=tp, fp=fp, fn=fn)
    return out


@dataclass(frozen=True)
class CombinedMetrics:
    flagged_precision: float
    flagged_recall: float
    pr_auc: float


def _combined_score(r: ScoredRecord) -> float:
    rule_max = max((c for _, c in r.fired_rules), default=0.0)
    return max(r.ml_prob, rule_max)


def compute_combined_metrics(
    records: Iterable[ScoredRecord], flag_threshold: float = 0.5
) -> CombinedMetrics:
    """Combined ML+rules: a txn is 'flagged' if any rule fired OR ml_prob >= threshold.

    PR-AUC is computed over `_combined_score` against `is_fraud`. With ML stubbed at 0.0
    and rule confidences fixed per rule, this collapses to a small number of operating
    points — informative but not directly comparable to a model trained on score-rich data.
    """
    records = list(records)
    flagged = [r for r in records if r.fired_rules or r.ml_prob >= flag_threshold]
    fraud = [r for r in records if r.is_fraud]
    tp = sum(1 for r in flagged if r.is_fraud)
    fp = sum(1 for r in flagged if not r.is_fraud)
    fn = sum(1 for r in fraud if r not in flagged)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0

    pr_auc = _pr_auc([_combined_score(r) for r in records], [r.is_fraud for r in records])
    return CombinedMetrics(flagged_precision=precision, flagged_recall=recall, pr_auc=pr_auc)


def _pr_auc(scores: list[float], labels: list[bool]) -> float:
    """Average precision: sum over rank k of (P(k) * delta-recall).

    Stdlib implementation so the harness has no required scientific deps. Matches
    sklearn.metrics.average_precision_score for the no-ties case; for ties it groups
    them and resolves at the higher recall point, which is the standard convention.
    """
    if not any(labels):
        return 0.0
    paired = sorted(zip(scores, labels), key=lambda x: -x[0])
    total_pos = sum(labels)
    tp = 0
    fp = 0
    prev_recall = 0.0
    ap = 0.0
    i = 0
    while i < len(paired):
        j = i
        while j < len(paired) and paired[j][0] == paired[i][0]:
            if paired[j][1]:
                tp += 1
            else:
                fp += 1
            j += 1
        precision = tp / (tp + fp)
        recall = tp / total_pos
        ap += precision * (recall - prev_recall)
        prev_recall = recall
        i = j
    return ap
