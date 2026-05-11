import importlib
import pkgutil
from dataclasses import dataclass
from pathlib import Path

from schemas import EntityContext, Transaction

RULES_DIR = Path(__file__).parent / "rules"


@dataclass(frozen=True)
class Rule:
    scheme_id: str
    confidence: float
    created_at: str
    author: str
    applies: callable


def _discover() -> list[Rule]:
    rules: list[Rule] = []
    if not RULES_DIR.exists():
        return rules
    for info in pkgutil.iter_modules([str(RULES_DIR)]):
        mod = importlib.import_module(f"rules.{info.name}")
        rules.append(
            Rule(
                scheme_id=mod.scheme_id,
                confidence=mod.confidence,
                created_at=mod.created_at,
                author=mod.author,
                applies=mod.applies,
            )
        )
    return rules


def evaluate(txn: Transaction, ctx: EntityContext) -> list[tuple[str, float]]:
    return [(r.scheme_id, r.confidence) for r in _discover() if r.applies(txn, ctx)]
