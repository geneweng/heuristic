# Reflector eval clusters

Hand-curated false-negative clusters used to evaluate the `propose_rule` prompt
*before* paying for live API calls or wiring the full reflector loop (#10).

## Status (toward #11 AC of 20 clusters)

| Type | Count | Files |
|---|---:|---|
| Valid clusters (should yield a rule) | 3 | `valid_*.json` |
| Adversarial (should be rejected by validator) | 2 | `adversarial_*.json` |
| **Total** | **5** / 20 | |

Path to 20: add valid clusters covering distinct schemes (promo abuse, refund
fraud, BNPL stacking, return-pump, merchant collusion, account takeover variants).
Each should be drawn from a real-looking run-log + analyst notes, not synthesized
from the rule definition itself (that would be tautological eval).

## How to add a cluster

1. Pick a scheme not yet represented.
2. Build 5–12 FN records that look distinct on `card_id`, `device_id`,
   `merchant_id` but share the structural signal that defines the scheme.
3. Write the analyst note for each — short, human, like a Slack message.
4. Set `expected_scheme_name` to the slug an analyst would name it.
5. Run `python -m eval --cluster eval_clusters/<your>.json` to dry-run, then
   `--live` (if `ANTHROPIC_API_KEY` is set) to check what Claude proposes.

## Why we keep adversarials in this corpus

The HL paper's update mechanism must refuse weak evidence. We test that with
clusters that *look* like a scheme but aren't — same-card-only (one bad
customer), too few FNs (premature), etc. The validator rejects these before
the API call.
