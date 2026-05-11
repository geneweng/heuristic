"""Turn a validated propose_rule proposal into committed source files.

Writes two files:

  - `<rules_dir>/<scheme_id>.py`              — the rule itself
  - `<tests_dir>/test_<scheme_id>.py`         — pos/neg tests from the proposal

Both follow the conventions of the hand-authored seed rules so the registry
picks them up identically.

The proposal's predicate_code is a function body (the contents of `def
applies(...)`), not a full function. We wrap it here. By the time materialize
runs, the predicate has already been compiled and exercised by the guards, so
syntax errors won't reach this layer.
"""

import json
import textwrap
from datetime import date
from pathlib import Path


_RULE_TEMPLATE = '''"""{description}"""

from decimal import Decimal

from schemas import EntityContext, Transaction

scheme_id = "{scheme_id}"
confidence = {confidence}
created_at = "{created_at}"
author = "{author}"


def applies(txn: Transaction, ctx: EntityContext) -> bool:
{body}
'''


_TEST_TEMPLATE = '''"""Tests for {scheme_id} (reflector-generated)."""

from datetime import datetime
from decimal import Decimal

from rules.{scheme_id} import applies
from schemas import EntityContext, Transaction


def _txn(**overrides):
    base = dict(
        txn_id="t",
        ts=datetime(2026, 5, 11, 12, 0, 0),
        amount=Decimal("10.00"),
        currency="USD",
        merchant_id="m_default",
        merchant_category="grocery",
        card_id="c_default",
        device_id="d_default",
        ip="1.2.3.4",
        country="US",
        approved=True,
    )
    base.update(overrides)
    if "amount" in overrides:
        base["amount"] = Decimal(str(overrides["amount"]))
    return Transaction(**base)


{tests}
'''


def _format_test(name: str, case: dict, expected: bool) -> str:
    """Render one pytest function from a test case in the proposal."""
    txn_kwargs = json.dumps(case.get("txn_overrides", {}))
    ctx_kwargs = json.dumps(case.get("ctx_overrides", {}))
    return textwrap.dedent(
        f"""
        def {name}():
            txn = _txn(**{txn_kwargs})
            ctx = EntityContext(**{ctx_kwargs})
            assert applies(txn, ctx) is {expected}
        """
    ).strip()


def materialize_rule(
    proposal: dict,
    rules_dir: Path,
    tests_dir: Path,
    *,
    today: date | None = None,
) -> tuple[Path, Path]:
    """Write the rule file and its test file. Returns (rule_path, test_path)."""
    scheme_id = proposal["scheme_id"]
    body = textwrap.indent(textwrap.dedent(proposal["predicate_code"]), "    ")

    rule_src = _RULE_TEMPLATE.format(
        description=proposal["description"].replace('"""', '"\\""'),  # cheap docstring safety
        scheme_id=scheme_id,
        confidence=float(proposal["confidence"]),
        created_at=(today or date.today()).isoformat(),
        author="reflector",
        body=body,
    )

    tests = []
    for i, case in enumerate(proposal.get("positive_tests", [])):
        tests.append(_format_test(f"test_positive_{i + 1}", case, True))
    for i, case in enumerate(proposal.get("negative_tests", [])):
        tests.append(_format_test(f"test_negative_{i + 1}", case, False))
    test_src = _TEST_TEMPLATE.format(scheme_id=scheme_id, tests="\n\n\n".join(tests))

    rules_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)
    rule_path = rules_dir / f"{scheme_id}.py"
    test_path = tests_dir / f"test_{scheme_id}.py"
    rule_path.write_text(rule_src)
    test_path.write_text(test_src)
    return rule_path, test_path
