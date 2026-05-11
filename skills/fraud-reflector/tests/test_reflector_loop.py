"""End-to-end test of the reflector loop using the build_fixture output."""

import json
from datetime import date
from pathlib import Path

import pytest

from reflector import find_false_negatives, reflect, stub_propose

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_BUILDER = REPO_ROOT / "data" / "reflect" / "build_fixture.py"


def _build_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """Run the build_fixture script into tmp_path and return (runs_dir, labels_path)."""
    runs_dir = tmp_path / "runs"
    labels_dir = tmp_path / "labels"
    runs_dir.mkdir()
    labels_dir.mkdir()

    # Run the builder but redirect its outputs into tmp by monkey-patching the
    # module-level paths. Simpler than spawning a subprocess.
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_fixture_under_test", FIXTURE_BUILDER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.RUNS_DIR = runs_dir
    mod.LABELS_PATH = labels_dir / "labels.jsonl"
    mod.main()
    return runs_dir, labels_dir / "labels.jsonl"


def test_find_false_negatives_from_fixture(tmp_path):
    runs_dir, labels = _build_fixture(tmp_path)
    fns = find_false_negatives(runs_dir, labels)
    assert len(fns) == 7
    assert all(fn.txn_id.startswith("fn_") for fn in fns)


def test_reflect_end_to_end_dry_run(tmp_path):
    runs_dir, labels = _build_fixture(tmp_path)
    rules_dir = tmp_path / "out_rules"
    tests_dir = tmp_path / "out_tests"
    attempts_log = tmp_path / "attempts.jsonl"

    report = reflect(
        runs_dir=runs_dir,
        labels_path=labels,
        rules_dir=rules_dir,
        tests_dir=tests_dir,
        attempts_log=attempts_log,
        today=date(2026, 5, 11),
    )

    assert report.clusters_found >= 1
    materialized = [r for r in report.results if r["action"] == "materialized"]
    assert materialized, f"expected at least one materialized rule, got {report.results}"

    # The materialized rule file must be syntactically valid Python.
    rule_path = Path(materialized[0]["rule_path"])
    compile(rule_path.read_text(), str(rule_path), "exec")

    # Attempts log must include at least one entry (the materialized rule).
    lines = attempts_log.read_text().splitlines()
    assert len(lines) >= 1
    assert all(json.loads(line)["status"] in {"passed", "blocked"} for line in lines)


def test_reflect_logs_token_usage(tmp_path):
    runs_dir, labels = _build_fixture(tmp_path)

    # Inject a propose_fn that returns deterministic usage.
    from reflector import stub_propose

    def fake_propose(cluster):
        result = stub_propose(cluster)
        # Override usage so we can assert specific tokens flow into the report
        from cost import Usage
        result["usage"] = Usage("claude-opus-4-7", input_tokens=1500, output_tokens=400)
        return result

    report = reflect(
        runs_dir=runs_dir,
        labels_path=labels,
        rules_dir=tmp_path / "rules",
        tests_dir=tmp_path / "tests",
        attempts_log=tmp_path / "attempts.jsonl",
        propose_fn=fake_propose,
        today=date(2026, 5, 11),
    )
    assert report.total_usage["input_tokens"] >= 1500
    assert report.total_usage["output_tokens"] >= 400
    assert report.total_usage["cost_usd"] > 0


def test_reflect_blocks_proposal_failing_guards(tmp_path):
    runs_dir, labels = _build_fixture(tmp_path)

    def bad_propose(cluster):
        result = stub_propose(cluster)
        # Inject an identity-feature literal — the guard must catch it.
        first_card = cluster.fn_records[0].txn["card_id"]
        result["input"]["predicate_code"] = f'return txn.card_id == "{first_card}"'
        return result

    report = reflect(
        runs_dir=runs_dir,
        labels_path=labels,
        rules_dir=tmp_path / "rules",
        tests_dir=tmp_path / "tests",
        attempts_log=tmp_path / "attempts.jsonl",
        propose_fn=bad_propose,
        today=date(2026, 5, 11),
    )
    blocked = [r for r in report.results if r["action"] == "blocked_by_guards"]
    assert blocked
    assert any("identity_features" == i["guard"] for i in blocked[0]["issues"])


def test_reflect_reverts_on_replay_regression(tmp_path):
    runs_dir, labels = _build_fixture(tmp_path)
    rules_dir = tmp_path / "rules"
    tests_dir = tmp_path / "tests"

    report = reflect(
        runs_dir=runs_dir,
        labels_path=labels,
        rules_dir=rules_dir,
        tests_dir=tests_dir,
        attempts_log=tmp_path / "attempts.jsonl",
        replay_fn=lambda: False,  # simulate replay failure
        today=date(2026, 5, 11),
    )
    reverted = [r for r in report.results if r["action"] == "reverted_after_replay_regression"]
    assert reverted, "expected a reverted entry when replay fails"
    # The rule + test files should have been deleted on revert.
    assert not any(rules_dir.glob("*.py")) or not any(tests_dir.glob("*.py"))
