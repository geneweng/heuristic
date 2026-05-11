"""Anti-overfitting guards for reflector-proposed rules (#15).

The reflector's biggest failure mode is a rule that perfectly fits the FN cluster
it was shown and nothing else. `validate_proposal()` runs four guards before any
PR is opened; any failure blocks the proposal and is appended to
`memory/attempts.jsonl`.

Guards (defense-in-depth — fail closed on the first issue, but report all):

1. **identity_features** — predicate code must not contain a string literal that
   matches any cited card_id / device_id / merchant_id / ip / bin. The prompt
   tells the model to avoid these, but we never trust the model on this.
2. **holdout_precision** — compile + run the predicate against a labeled holdout
   the reflector never saw. Reject if precision < floor OR support < floor.
3. **fp_cap** — same predicate against legitimate-only traffic; reject if fire
   rate > fp_cap_ratio. Prevents catastrophic over-blocking.
4. **redundancy** — if any existing rule already covers > redundancy_max_overlap
   of the cited FNs, reject and (in #10) re-prompt for an edit to that rule.

SECURITY NOTE — predicate execution. We exec() proposal code in a restricted
namespace exposing only `Transaction`, `EntityContext`, and `Decimal`. This is
acceptable for the POC (own pipeline, own infra). Production must run guards
in a real sandbox (Docker/firejail/Pyodide) — the model is not trusted code.
"""

import json
import re
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable

from schemas import EntityContext, Transaction

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ATTEMPTS_LOG = REPO_ROOT / "memory" / "attempts.jsonl"


# --- config -------------------------------------------------------------------


@dataclass(frozen=True)
class GuardFloors:
    holdout_precision: float = 0.85
    holdout_support: int = 10
    fp_cap_ratio: float = 0.001         # 0.1% of legit traffic
    redundancy_max_overlap: float = 0.7


@dataclass(frozen=True)
class LabeledRecord:
    """A holdout/legit record: a built Transaction + EntityContext + label."""

    txn: Transaction
    ctx: EntityContext
    true_scheme_id: str | None
    is_fraud: bool


@dataclass(frozen=True)
class ExistingRule:
    scheme_id: str
    applies: Callable[[Transaction, EntityContext], bool]


@dataclass(frozen=True)
class GuardConfig:
    holdout: list[LabeledRecord] = field(default_factory=list)
    legit: list[LabeledRecord] = field(default_factory=list)
    existing_rules: list[ExistingRule] = field(default_factory=list)
    cited_records: list[LabeledRecord] = field(default_factory=list)
    floors: GuardFloors = field(default_factory=GuardFloors)


# --- predicate compilation ----------------------------------------------------


def compile_predicate(predicate_code: str) -> Callable[[Transaction, EntityContext], bool]:
    """Wrap a proposal's predicate body in `def applies()` and exec it.

    See SECURITY NOTE at module top — POC-grade isolation only.
    """
    body = textwrap.indent(textwrap.dedent(predicate_code), "    ")
    src = (
        "def applies(txn, ctx):\n"
        f"{body}\n"
    )
    ns: dict = {"Decimal": Decimal, "Transaction": Transaction, "EntityContext": EntityContext}
    exec(compile(src, "<proposal>", "exec"), ns)
    fn = ns["applies"]

    def _safe_apply(txn: Transaction, ctx: EntityContext) -> bool:
        try:
            return bool(fn(txn, ctx))
        except Exception:
            return False  # malformed predicates are FP=0 — they'll trip support floor instead

    return _safe_apply


# --- guards -------------------------------------------------------------------


_IDENTITY_FIELDS = ("card_id", "device_id", "merchant_id", "ip", "bin", "txn_id")


def _check_identity_features(proposal: dict, cfg: GuardConfig) -> str | None:
    """Reject if predicate_code contains a string literal matching a cited
    identity field."""
    code = proposal["predicate_code"]
    cited = cfg.cited_records
    for rec in cited:
        txn = rec.txn
        for field_name in _IDENTITY_FIELDS:
            val = getattr(txn, field_name, None)
            if val is None or not isinstance(val, str) or len(val) < 3:
                continue
            if re.search(rf"[\"']{re.escape(val)}[\"']", code):
                return f"predicate references identity literal {field_name}={val!r}"
    return None


def _check_holdout_precision(proposal: dict, cfg: GuardConfig) -> str | None:
    if not cfg.holdout:
        return None  # skip if no holdout supplied
    fn = compile_predicate(proposal["predicate_code"])
    fires = [r for r in cfg.holdout if fn(r.txn, r.ctx)]
    tp = sum(1 for r in fires if r.is_fraud)
    precision = tp / len(fires) if fires else 0.0
    support = tp
    if support < cfg.floors.holdout_support:
        return f"holdout support {support} < floor {cfg.floors.holdout_support}"
    if precision < cfg.floors.holdout_precision:
        return f"holdout precision {precision:.2f} < floor {cfg.floors.holdout_precision}"
    return None


def _check_fp_cap(proposal: dict, cfg: GuardConfig) -> str | None:
    if not cfg.legit:
        return None
    fn = compile_predicate(proposal["predicate_code"])
    fp = sum(1 for r in cfg.legit if fn(r.txn, r.ctx))
    rate = fp / len(cfg.legit)
    if rate > cfg.floors.fp_cap_ratio:
        return (
            f"FP rate {rate:.4f} on legit traffic exceeds cap "
            f"{cfg.floors.fp_cap_ratio:.4f} ({fp}/{len(cfg.legit)})"
        )
    return None


def _check_redundancy(proposal: dict, cfg: GuardConfig) -> str | None:
    if not cfg.cited_records or not cfg.existing_rules:
        return None
    cited_n = len(cfg.cited_records)
    for rule in cfg.existing_rules:
        hits = sum(1 for r in cfg.cited_records if rule.applies(r.txn, r.ctx))
        overlap = hits / cited_n
        if overlap > cfg.floors.redundancy_max_overlap:
            return (
                f"existing rule {rule.scheme_id!r} already fires on "
                f"{hits}/{cited_n} ({overlap:.0%}) of the cited FNs — propose an edit instead"
            )
    return None


GUARDS = [
    ("identity_features", _check_identity_features),
    ("holdout_precision", _check_holdout_precision),
    ("fp_cap", _check_fp_cap),
    ("redundancy", _check_redundancy),
]


# --- public API ---------------------------------------------------------------


def validate_proposal(proposal: dict, cfg: GuardConfig) -> list[dict]:
    """Run every guard. Returns a list of {guard, message} for those that tripped.

    Returns an empty list iff the proposal is ready for `gh pr create`.
    """
    issues: list[dict] = []
    for name, check in GUARDS:
        try:
            msg = check(proposal, cfg)
        except Exception as e:
            msg = f"guard raised: {e}"
        if msg:
            issues.append({"guard": name, "message": msg})
    return issues


def log_attempt(
    proposal: dict,
    issues: list[dict],
    *,
    path: Path = DEFAULT_ATTEMPTS_LOG,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> None:
    """Append a reflector attempt to memory/attempts.jsonl.

    Per the HL update mechanism: every attempt (passed or blocked) becomes part
    of the system's memory so future runs can avoid repeating the same mistakes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": now().isoformat(),
        "scheme_id": proposal.get("scheme_id"),
        "status": "blocked" if issues else "passed",
        "issues": issues,
        "cited_txn_ids": proposal.get("cited_txn_ids", []),
    }
    with path.open("a") as f:
        f.write(json.dumps(rec) + "\n")
