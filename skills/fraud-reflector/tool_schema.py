"""Anthropic tool definitions for the reflector.

Per #11 AC: "Prompt enforces output schema via tool definition, not free-text parsing."
The model can call exactly one of:

  - propose_rule       — submit a fully-formed rule proposal
  - decline_rule_proposal — refuse the cluster with a stated reason

Both are passed as `tools=[...]` on the Anthropic messages.create() call.
"""

PROPOSE_RULE_TOOL = {
    "name": "propose_rule",
    "description": (
        "Propose a single new fraud detection rule based on a cluster of false "
        "negatives. The rule must generalize beyond the cited evidence and avoid "
        "all identity features (card_id, device_id, merchant_id, ip, bin)."
    ),
    "input_schema": {
        "type": "object",
        "required": [
            "scheme_id",
            "description",
            "rationale",
            "predicate_code",
            "positive_tests",
            "negative_tests",
            "cited_txn_ids",
            "confidence",
        ],
        "properties": {
            "scheme_id": {
                "type": "string",
                "pattern": "^[a-z][a-z0-9_]*_v[0-9]+$",
                "description": (
                    "Snake-case slug ending in _vN. Must name the scheme (the "
                    "*pattern*), not the rule number. Example: "
                    "'gift_card_micro_drain_v1'."
                ),
            },
            "description": {
                "type": "string",
                "minLength": 60,
                "description": (
                    "2-5 sentence plain-English docstring describing the scheme "
                    "this rule catches. Written for an analyst reviewing the PR."
                ),
            },
            "rationale": {
                "type": "string",
                "minLength": 40,
                "description": (
                    "Why this generalizes beyond the cited cluster. What "
                    "structural pattern does it capture?"
                ),
            },
            "predicate_code": {
                "type": "string",
                "description": (
                    "Body of `def applies(txn: Transaction, ctx: EntityContext) "
                    "-> bool:`. Must reference only schema fields. Must NOT "
                    "contain string literals matching any cited card_id, "
                    "device_id, merchant_id, ip, or bin."
                ),
            },
            "positive_tests": {
                "type": "array",
                "minItems": 3,
                "items": {
                    "type": "object",
                    "required": ["txn_overrides", "ctx_overrides", "expected_fire"],
                    "properties": {
                        "txn_overrides": {"type": "object"},
                        "ctx_overrides": {"type": "object"},
                        "expected_fire": {"const": True},
                    },
                },
            },
            "negative_tests": {
                "type": "array",
                "minItems": 3,
                "items": {
                    "type": "object",
                    "required": ["txn_overrides", "ctx_overrides", "expected_fire"],
                    "properties": {
                        "txn_overrides": {"type": "object"},
                        "ctx_overrides": {"type": "object"},
                        "expected_fire": {"const": False},
                    },
                },
            },
            "cited_txn_ids": {
                "type": "array",
                "minItems": 5,
                "items": {"type": "string"},
                "description": "fn_txn_ids from the cluster that the rule covers.",
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": (
                    "Per calibration: >=0.9 unambiguous, 0.7-0.9 strong, 0.5-0.7 "
                    "weak (review-only). <0.5 should be a decline."
                ),
            },
        },
    },
}


DECLINE_TOOL = {
    "name": "decline_rule_proposal",
    "description": (
        "Refuse to propose a rule because the cluster is too weak, too small, "
        "covered by an existing rule, or otherwise unjustified."
    ),
    "input_schema": {
        "type": "object",
        "required": ["reason"],
        "properties": {
            "reason": {
                "type": "string",
                "minLength": 20,
                "description": (
                    "Specific reason: too few FNs, single-card cluster, "
                    "duplicates existing rule X, etc."
                ),
            },
        },
    },
}


REFLECTOR_TOOLS = [PROPOSE_RULE_TOOL, DECLINE_TOOL]
