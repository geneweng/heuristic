from rules.geo_country_jump_v1 import applies, scheme_id
from schemas import EntityContext


def test_metadata():
    assert scheme_id == "geo_country_jump_v1"


# --- positives ---

def test_country_change_within_30_min_fires(make_txn):
    txn = make_txn(country="DE")
    ctx = EntityContext(prev_country="US", card_seconds_since_last_txn=600)
    assert applies(txn, ctx) is True


def test_country_change_at_boundary_fires(make_txn):
    txn = make_txn(country="JP")
    ctx = EntityContext(prev_country="US", card_seconds_since_last_txn=1799)
    assert applies(txn, ctx) is True


def test_country_change_at_one_second_fires(make_txn):
    txn = make_txn(country="BR")
    ctx = EntityContext(prev_country="US", card_seconds_since_last_txn=1)
    assert applies(txn, ctx) is True


# --- negatives ---

def test_same_country_does_not_fire(make_txn):
    txn = make_txn(country="US")
    ctx = EntityContext(prev_country="US", card_seconds_since_last_txn=60)
    assert applies(txn, ctx) is False


def test_country_change_after_30_min_does_not_fire(make_txn):
    txn = make_txn(country="DE")
    ctx = EntityContext(prev_country="US", card_seconds_since_last_txn=1800)
    assert applies(txn, ctx) is False


def test_first_seen_card_does_not_fire(make_txn):
    txn = make_txn(country="DE")
    ctx = EntityContext(prev_country=None, card_seconds_since_last_txn=None)
    assert applies(txn, ctx) is False
