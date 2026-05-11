"""Five hand-crafted overfitting attempts, one per guard.

Each test builds a proposal that an honest reflector should never make, plus a
GuardConfig that gives the right guard something to bite on, then asserts
exactly that guard trips.
"""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from guards import (
    ExistingRule,
    GuardConfig,
    GuardFloors,
    LabeledRecord,
    compile_predicate,
    log_attempt,
    validate_proposal,
)
from rules.card_testing_burst_v1 import applies as card_testing_applies
from schemas import EntityContext, Transaction


# --- helpers ------------------------------------------------------------------


def _txn(txn_id: str, **overrides) -> Transaction:
    base = {
        "txn_id": txn_id,
        "ts": datetime(2026, 5, 1, 12, 0, 0),
        "amount": Decimal("10.00"),
        "currency": "USD",
        "merchant_id": "m_default",
        "merchant_category": "grocery",
        "card_id": f"c_{txn_id}",
        "device_id": f"d_{txn_id}",
        "ip": "1.2.3.4",
        "country": "US",
        "approved": True,
    }
    base.update(overrides)
    return Transaction(**base)


def _labeled(txn_id: str, *, ctx: EntityContext | None = None, fraud: bool = False, scheme: str | None = None, **txn_overrides) -> LabeledRecord:
    return LabeledRecord(
        txn=_txn(txn_id, **txn_overrides),
        ctx=ctx or EntityContext(),
        true_scheme_id=scheme,
        is_fraud=fraud,
    )


def _proposal(predicate: str, **overrides) -> dict:
    base = {
        "scheme_id": "test_scheme_v1",
        "description": "test",
        "rationale": "test",
        "predicate_code": predicate,
        "positive_tests": [],
        "negative_tests": [],
        "cited_txn_ids": ["a", "b", "c", "d", "e"],
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


def _guards_tripped(issues: list[dict]) -> set[str]:
    return {i["guard"] for i in issues}


# --- happy path ---------------------------------------------------------------


def test_clean_proposal_passes_all_guards():
    # Predicate that fires on >$500 high-amount + new device on aged card.
    # Holdout has many such fraud cases; legit traffic doesn't trip it.
    fraud_pop = [
        _labeled(
            f"hf_{i}",
            ctx=EntityContext(card_age_days=200, current_device_seen_before_for_card=False),
            fraud=True,
            amount=Decimal("700.00"),
        )
        for i in range(12)
    ]
    legit_pop = [_labeled(f"hb_{i}", amount=Decimal("12.00")) for i in range(2000)]

    proposal = _proposal(
        "return (ctx.card_age_days > 90 and "
        "not ctx.current_device_seen_before_for_card and "
        "txn.amount > Decimal('600'))"
    )
    cfg = GuardConfig(holdout=fraud_pop + legit_pop, legit=legit_pop)
    assert validate_proposal(proposal, cfg) == []


# --- five overfitting attempts ------------------------------------------------


def test_identity_card_id_literal_tripped():
    cited = [_labeled("x", card_id="c_one_bad_actor", fraud=True) for _ in range(5)]
    proposal = _proposal('return txn.card_id == "c_one_bad_actor"')
    cfg = GuardConfig(cited_records=cited)
    issues = validate_proposal(proposal, cfg)
    assert "identity_features" in _guards_tripped(issues)


def test_identity_merchant_literal_tripped():
    cited = [_labeled(f"y{i}", merchant_id="m_specific_merchant") for i in range(5)]
    proposal = _proposal('return txn.merchant_id == "m_specific_merchant"')
    cfg = GuardConfig(cited_records=cited)
    issues = validate_proposal(proposal, cfg)
    assert "identity_features" in _guards_tripped(issues)


def test_low_holdout_precision_tripped():
    # Predicate fires on US-country grocery txns — broad and barely correlated.
    fraud = [_labeled(f"f{i}", fraud=True) for i in range(11)]  # support is fine
    legit = [_labeled(f"l{i}", amount=Decimal(str(20 + i))) for i in range(200)]
    proposal = _proposal('return txn.country == "US" and txn.merchant_category == "grocery"')
    cfg = GuardConfig(
        holdout=fraud + legit,
        floors=GuardFloors(holdout_precision=0.85, holdout_support=5),
    )
    issues = validate_proposal(proposal, cfg)
    assert "holdout_precision" in _guards_tripped(issues)


def test_fp_cap_tripped():
    # Predicate fires on every legit txn — 100% FP rate.
    legit = [_labeled(f"lc_{i}") for i in range(500)]
    fraud = [_labeled(f"fc_{i}", fraud=True) for i in range(20)]
    proposal = _proposal("return True")
    cfg = GuardConfig(
        holdout=fraud + legit,
        legit=legit,
        floors=GuardFloors(holdout_precision=0.0, holdout_support=0, fp_cap_ratio=0.001),
    )
    issues = validate_proposal(proposal, cfg)
    assert "fp_cap" in _guards_tripped(issues)


def test_redundancy_with_existing_rule_tripped():
    # Cite 6 FNs that all match an existing rule's signal. Use the real
    # card_testing_burst_v1 rule for authenticity.
    cited = [
        _labeled(
            f"r{i}",
            ctx=EntityContext(card_txn_count_60s=7, card_min_amount_60s=Decimal("0.50")),
            fraud=True,
        )
        for i in range(6)
    ]
    proposal = _proposal("return ctx.card_txn_count_60s >= 4")
    cfg = GuardConfig(
        cited_records=cited,
        existing_rules=[
            ExistingRule(scheme_id="card_testing_burst_v1", applies=card_testing_applies)
        ],
    )
    issues = validate_proposal(proposal, cfg)
    msg = next(i for i in issues if i["guard"] == "redundancy")
    assert "card_testing_burst_v1" in msg["message"]


# --- predicate compiler & attempt logging ------------------------------------


def test_compile_predicate_evaluates_against_real_types():
    fn = compile_predicate("return ctx.card_decline_count_1h >= 2 and txn.approved")
    txn = _txn("t1")
    assert fn(txn, EntityContext(card_decline_count_1h=3)) is True
    assert fn(txn, EntityContext(card_decline_count_1h=1)) is False


def test_compile_predicate_swallows_runtime_errors():
    # A broken predicate must not crash the guard pipeline.
    fn = compile_predicate("return txn.this_attr_does_not_exist > 0")
    assert fn(_txn("t1"), EntityContext()) is False


def test_log_attempt_appends_jsonl(tmp_path):
    log = tmp_path / "attempts.jsonl"
    pinned = lambda: datetime(2026, 5, 11, 14, 0, 0, tzinfo=timezone.utc)
    log_attempt(_proposal("return True"), [{"guard": "fp_cap", "message": "x"}], path=log, now=pinned)
    log_attempt(_proposal("return False"), [], path=log, now=pinned)
    lines = log.read_text().splitlines()
    assert len(lines) == 2

    import json

    a, b = (json.loads(line) for line in lines)
    assert a["status"] == "blocked"
    assert a["issues"][0]["guard"] == "fp_cap"
    assert b["status"] == "passed"
