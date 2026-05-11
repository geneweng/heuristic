# Run log record schema

Each line in `runs/<date>.jsonl` is one transaction processed by the orchestrator.
Append-only — never rewrite history; old records are evidence the reflector reads to
propose new rules.

## Record

```jsonc
{
  "ts": "2026-05-11T14:23:01.000+00:00",   // decision time, UTC
  "txn": {                                  // full Transaction (skills/common/schemas.py)
    "txn_id": "...",
    "ts": "2026-05-11T14:22:58",            // original txn time (may differ from decision ts)
    "amount": "12.50",
    "currency": "USD",
    "merchant_id": "...",
    "merchant_category": "grocery",
    "card_id": "...",
    "device_id": "...",
    "ip": "1.2.3.4",
    "country": "US",
    "approved": true,
    "city": null,
    "bin": null
  },
  "ctx": { /* full EntityContext at decision time */ },
  "ml_prob": 0.0,
  "fired_rules": [["scheme_id", 0.95], ...],
  "decision": "allow"                       // "block" | "review" | "allow"
}
```

## Why ctx is logged

The reflector clusters false negatives by feature similarity. Logging the full context
at decision time means the reflector can replay the exact state the rules saw, without
having to rebuild it from history — and changes to `build_context()` later don't
invalidate old runs.

## Why decision time, not txn time, is the top-level `ts`

The reflector partitions runs by *when we observed and decided*, not by *when the txn
happened*. A back-dated or stream-replayed txn still belongs in today's log.
