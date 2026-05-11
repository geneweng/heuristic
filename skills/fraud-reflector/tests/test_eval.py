from pathlib import Path

from clusters import load_cluster
from eval import build_prompt, propose_rule

CLUSTERS_DIR = Path(__file__).resolve().parents[1] / "eval_clusters"


def test_build_prompt_includes_cluster_and_schemas():
    cluster = load_cluster(CLUSTERS_DIR / "valid_gift_card_micro_drain_v1.json")
    prompt = build_prompt(cluster)
    # Static parts from propose_rule.md
    assert "Propose Fraud Rule" in prompt
    assert "decline_rule_proposal" in prompt
    # Schema docs
    assert "EntityContext" in prompt
    assert "card_id, txn_id, merchant_id" in prompt
    # Cluster injection
    assert cluster.cluster_id in prompt
    assert cluster.fn_records[0].txn_id in prompt
    # Existing-rules section is present even when there are rules
    assert "Existing rules" in prompt


def test_propose_rule_dry_run_on_valid_cluster():
    cluster = load_cluster(CLUSTERS_DIR / "valid_promo_code_abuse_v1.json")
    result = propose_rule(cluster, live=False)
    assert result["action"] == "dry_run"
    assert result["prompt_chars"] > 0
    assert "propose_rule" in result["tools"]
    assert "decline_rule_proposal" in result["tools"]


def test_propose_rule_rejects_adversarial_too_few():
    cluster = load_cluster(CLUSTERS_DIR / "adversarial_too_few.json")
    result = propose_rule(cluster, live=False)
    assert result["action"] == "rejected_by_validator"
    assert any("too few" in i for i in result["issues"])


def test_propose_rule_rejects_adversarial_single_customer():
    cluster = load_cluster(CLUSTERS_DIR / "adversarial_single_customer.json")
    result = propose_rule(cluster, live=False)
    assert result["action"] == "rejected_by_validator"
    assert any("card_id" in i for i in result["issues"])
