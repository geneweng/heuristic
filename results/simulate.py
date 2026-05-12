"""End-to-end POC simulation (#14).

A 14-day simulated timeline:

  - Day 3: scheme A (new_bin_attack) injected
  - Day 5: scheme B (session_replay) injected
  - Day 7: scheme C (synthetic_id_ring) injected
  - Each scheme's labels arrive 12h after injection
  - The reflector wakes on each subsequent day; once a scheme has been
    labeled, its FNs form a cluster and a rule is materialized

Per-day recall on each scheme is computed against the live rule set
(seed rules + every rule materialized so far). Output:

  - results/output/timeline.jsonl  — one record per day, machine-readable
  - results/output/SUMMARY.md      — written narrative against #14's targets
  - results/output/headline.png    — per-scheme recall over time (if matplotlib)

The simulation is fully offline (uses `stub_propose`); no API key required.
"""

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from clustering import cluster_fns
from clusters import FNCluster, FNRecord
from data.injectors import INJECTORS
from data.injectors.new_bin_attack import SCHEME_ID as A_ID
from data.injectors.session_replay import SCHEME_ID as B_ID
from data.injectors.synthetic_id_ring import SCHEME_ID as C_ID
from guards import compile_predicate
from registry import _discover
from reflector import reflect, stub_propose
from schemas import EntityContext, Transaction

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "results" / "output"
BASE_DAY = datetime(2026, 5, 1, 9, 0, 0, tzinfo=timezone.utc)
SIM_DAYS = 14

INJECTION_SCHEDULE = [
    (3, "new_bin_attack", A_ID),
    (5, "session_replay", B_ID),
    (7, "synthetic_id_ring", C_ID),
]

SCHEME_NAMES = {A_ID: "A: new_bin_attack", B_ID: "B: session_replay", C_ID: "C: synthetic_id_ring"}


@dataclass
class DayMetric:
    day: int
    iso_date: str
    scheme_recall: dict        # {scheme_id: recall_float}
    materialized_rules: list   # cumulative
    new_rules_today: list


def _record_to_txn(r: dict) -> Transaction:
    fields = dict(
        txn_id=r["txn_id"],
        ts=datetime.fromisoformat(r["ts"]),
        amount=Decimal(r["amount"]),
        currency=r["currency"],
        merchant_id=r["merchant_id"],
        merchant_category=r["merchant_category"],
        card_id=r["card_id"],
        device_id=r["device_id"],
        ip=r["ip"],
        country=r["country"],
        approved=r["approved"],
        city=r.get("city"),
        bin=r.get("bin"),
    )
    return Transaction(**fields)


def _record_to_ctx(ctx_dict: dict) -> EntityContext:
    fields = {}
    for k, v in ctx_dict.items():
        if v is None:
            continue
        if k in ("card_amount_24h", "card_min_amount_60s"):
            fields[k] = Decimal(str(v))
        else:
            fields[k] = v
    return EntityContext(**fields)


def _compute_recall(scheme_txns: list[tuple[Transaction, EntityContext]], applies_fns: list) -> float:
    if not scheme_txns:
        return 0.0
    caught = 0
    for txn, ctx in scheme_txns:
        if any(fn(txn, ctx) for fn in applies_fns):
            caught += 1
    return caught / len(scheme_txns)


def simulate(output_dir: Path = OUTPUT_DIR, *, propose_fn=stub_propose) -> dict:
    """Run the 14-day timeline; return summary dict and write artifacts to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sim_runs_dir = output_dir / "sim_runs"
    sim_labels_dir = output_dir / "sim_labels"
    sim_rules_dir = output_dir / "sim_rules"
    sim_tests_dir = output_dir / "sim_tests"
    for d in (sim_runs_dir, sim_labels_dir, sim_rules_dir, sim_tests_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Pre-generate all injected fraud and stash it by day.
    by_scheme: dict[str, list[tuple[dict, dict]]] = {}
    for day, name, sid in INJECTION_SCHEDULE:
        injector = INJECTORS[name]
        start_ts = BASE_DAY + timedelta(days=day)
        by_scheme[sid] = injector(start_ts)

    # Per-scheme (txn, ctx) pairs we'll score for recall each day.
    scheme_eval_set: dict[str, list[tuple[Transaction, EntityContext]]] = {
        sid: [(_record_to_txn(rr["txn"]), _record_to_ctx(rr["ctx"])) for rr, _ in pairs]
        for sid, pairs in by_scheme.items()
    }

    seed_applies = [r.applies for r in _discover()]
    active_applies = list(seed_applies)
    timeline: list[DayMetric] = []

    for day in range(1, SIM_DAYS + 1):
        # 1) Compute current per-scheme recall against active rules
        recall = {sid: _compute_recall(s, active_applies) for sid, s in scheme_eval_set.items()}

        # 2) Build a labeled-by-now runs+labels view and try to reflect
        runs_file = sim_runs_dir / f"day_{day:02d}.jsonl"
        labels_file = sim_labels_dir / f"day_{day:02d}.jsonl"
        runs_today: list[dict] = []
        labels_today: list[dict] = []
        for inj_day, _name, sid in INJECTION_SCHEDULE:
            if day < inj_day:
                continue
            for rr, lr in by_scheme[sid]:
                runs_today.append(rr)
                # Label arrives 12h after the txn, so it's available the next day.
                if day > inj_day:
                    labels_today.append(lr)
        runs_file.write_text("\n".join(json.dumps(r) for r in runs_today) + "\n" if runs_today else "")
        labels_file.write_text(
            "\n".join(json.dumps(l) for l in labels_today) + "\n" if labels_today else ""
        )

        new_rules: list[dict] = []
        if labels_today:
            day_rules_dir = sim_rules_dir / f"day_{day:02d}"
            day_tests_dir = sim_tests_dir / f"day_{day:02d}"
            report = reflect(
                runs_dir=sim_runs_dir,
                labels_path=labels_file,
                rules_dir=day_rules_dir,
                tests_dir=day_tests_dir,
                propose_fn=propose_fn,
                attempts_log=output_dir / "attempts.jsonl",
                today=date(2026, 5, 1) + timedelta(days=day - 1),
                replay_fn=lambda: True,
            )
            for result in report.results:
                if result["action"] == "materialized":
                    rule_path = Path(result["rule_path"])
                    ns: dict = {}
                    exec(rule_path.read_text(), ns)
                    active_applies.append(ns["applies"])
                    new_rules.append({"scheme_id": rule_path.stem, "predicate": "see " + str(rule_path)})

        recall_after = {sid: _compute_recall(s, active_applies) for sid, s in scheme_eval_set.items()}
        timeline.append(
            DayMetric(
                day=day,
                iso_date=(BASE_DAY + timedelta(days=day - 1)).date().isoformat(),
                scheme_recall=recall_after,
                materialized_rules=[r["scheme_id"] for r in new_rules],
                new_rules_today=new_rules,
            )
        )

    _write_timeline(output_dir / "timeline.jsonl", timeline)
    summary = _build_summary(timeline)
    (output_dir / "SUMMARY.md").write_text(summary)
    _try_write_headline_chart(output_dir / "headline.png", timeline)
    return {
        "days": len(timeline),
        "final_recall": timeline[-1].scheme_recall,
        "output_dir": str(output_dir),
    }


def _write_timeline(path: Path, timeline: list[DayMetric]) -> None:
    path.write_text("\n".join(json.dumps(asdict(d)) for d in timeline) + "\n")


def _first_day_above(timeline: list[DayMetric], scheme_id: str, floor: float = 0.8) -> int | None:
    for m in timeline:
        if m.scheme_recall.get(scheme_id, 0) >= floor:
            return m.day
    return None


def _build_summary(timeline: list[DayMetric]) -> str:
    lines = [
        "# POC Results (simulation)",
        "",
        "Synthetic 14-day timeline against three injected schemes the frozen ML and seed rules miss by design. Reflector ran in offline (stub) mode — no Claude API call — so this measures the *plumbing* of the HL loop, not Claude's rule-authoring quality. Live-mode numbers will replace this once `ANTHROPIC_API_KEY` is wired in CI.",
        "",
        "## Headline",
        "",
        "| Scheme | Injected (day) | First labeled (day) | First detection ≥ 80% (day) | Time-to-detection |",
        "|---|---:|---:|---:|---|",
    ]
    for inj_day, _name, sid in INJECTION_SCHEDULE:
        labeled_day = inj_day + 1
        first_caught = _first_day_above(timeline, sid)
        ttd = f"{first_caught - labeled_day}d" if first_caught else "not caught"
        first_str = str(first_caught) if first_caught is not None else "—"
        lines.append(
            f"| {SCHEME_NAMES[sid]} | {inj_day} | {labeled_day} | {first_str} | {ttd} |"
        )

    lines.extend([
        "",
        "## Per-day recall",
        "",
        "| Day | " + " | ".join(SCHEME_NAMES[sid] for _, _, sid in INJECTION_SCHEDULE) + " |",
        "|---|" + "---|" * len(INJECTION_SCHEDULE),
    ])
    for m in timeline:
        cells = [f"{m.scheme_recall.get(sid, 0):.2f}" for _, _, sid in INJECTION_SCHEDULE]
        lines.append(f"| {m.day} | " + " | ".join(cells) + " |")

    lines.extend([
        "",
        "## Against #14's targets",
        "",
        "- **Time-to-detection < 48h** — see headline table.",
        "- **Rule precision ≥ 0.85 on holdout** — not measured in stub mode (no holdout split until #2).",
        "- **Analyst approval rate ≥ 0.60** — not measured (no live PRs).",
        "- **No regression on prior schemes** — seed rules unchanged across all 14 days.",
        "- **Cost per merged rule** — $0.00 in stub mode; populated when live runs land.",
    ])
    return "\n".join(lines) + "\n"


def _try_write_headline_chart(path: Path, timeline: list[DayMetric]) -> None:
    """Per-scheme recall over time with injection points marked. Skips gracefully
    if matplotlib isn't installed."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return

    days = [m.day for m in timeline]
    fig, ax = plt.subplots(figsize=(9, 5))
    for inj_day, _name, sid in INJECTION_SCHEDULE:
        values = [m.scheme_recall.get(sid, 0) for m in timeline]
        ax.plot(days, values, marker="o", label=SCHEME_NAMES[sid])
        ax.axvline(x=inj_day, linestyle="--", alpha=0.25)
        ax.annotate(
            f"inject day {inj_day}",
            xy=(inj_day, 0.05),
            rotation=90,
            fontsize=8,
            alpha=0.6,
        )
    ax.set_xlabel("Simulated day")
    ax.set_ylabel("Per-scheme recall (against active rules)")
    ax.set_ylim(-0.05, 1.1)
    ax.set_title("HL POC: per-scheme recall over time")
    ax.legend(loc="lower right")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> int:
    summary = simulate()
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
