"""Streamlit analyst UI — thin glue over queue.py / labels_io.py / pr_review.py.

Run via `make ui` (sets PYTHONPATH and invokes `streamlit run`).
"""

import os
from pathlib import Path

import streamlit as st

from labels_io import append_label
from pr_review import (
    approve_pr,
    get_pr_diff,
    list_open_reflector_prs,
    reject_reflector_pr,
)
from queue import build_queue

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = Path(os.environ.get("ANALYST_RUNS_DIR", REPO_ROOT / "runs"))
LABELS_PATH = Path(os.environ.get("ANALYST_LABELS_PATH", REPO_ROOT / "labels" / "labels.jsonl"))
REVIEWER_ID = os.environ.get("ANALYST_USER") or os.environ.get("USER", "anonymous")


st.set_page_config(page_title="Fraud Analyst", layout="wide")
st.sidebar.markdown(f"**Reviewer:** `{REVIEWER_ID}`")
page = st.sidebar.radio("Page", ["Labeling Queue", "PR Review"])


def _render_labeling_queue() -> None:
    st.title("Labeling Queue")
    queue = build_queue(RUNS_DIR, LABELS_PATH)
    st.caption(f"{len(queue)} flagged txns awaiting review · runs: `{RUNS_DIR}` · labels: `{LABELS_PATH}`")

    if not queue:
        st.info("Queue is empty. Run `make stream` to produce flagged txns.")
        return

    for rec in queue[:50]:  # cap for responsiveness
        txn = rec["txn"]
        ctx = rec.get("ctx", {})
        txn_id = txn["txn_id"]

        with st.container(border=True):
            top = st.columns([2, 3, 2])
            top[0].markdown(f"**txn_id**: `{txn_id}`")
            top[1].markdown(
                f"**decision**: `{rec['decision']}` · "
                f"**ml_prob**: {rec.get('ml_prob', 0):.2f} · "
                f"**rules**: {[r[0] for r in rec.get('fired_rules', [])] or '—'}"
            )
            top[2].markdown(f"**when**: {rec.get('ts', '')[:19]}")

            st.json({"txn": txn, "ctx": ctx}, expanded=False)

            note = st.text_input(
                "Analyst note (cited if a rule is later proposed):",
                key=f"note_{txn_id}",
                placeholder="What pattern do you see?",
            )
            cols = st.columns(4)
            for col, label, color in zip(
                cols[:3],
                ("fraud", "legit", "unsure"),
                ("primary", "secondary", "secondary"),
            ):
                if col.button(label.title(), key=f"{label}_{txn_id}", type=color):
                    append_label(
                        LABELS_PATH,
                        txn_id=txn_id,
                        label=label,
                        note=note,
                        reviewer_id=REVIEWER_ID,
                    )
                    st.success(f"Labeled {txn_id} = {label}")
                    st.rerun()


def _render_pr_review() -> None:
    st.title("Reflector PR Review")
    try:
        prs = list_open_reflector_prs()
    except Exception as e:
        st.error(f"`gh pr list` failed: {e}")
        return

    st.caption(f"{len(prs)} open reflector PR(s)")
    if not prs:
        st.info("No open reflector PRs. Run `make reflect --live --open-pr` to produce one.")
        return

    for pr in prs:
        with st.container(border=True):
            st.markdown(f"### [#{pr.number}]({pr.url}) — `{pr.title}`")
            st.markdown(pr.body or "_(no body)_")
            with st.expander("Diff"):
                try:
                    st.code(get_pr_diff(pr.number), language="diff")
                except Exception as e:
                    st.error(f"diff failed: {e}")

            reason = st.text_input(
                "Rejection reason (required if rejecting):",
                key=f"reason_{pr.number}",
            )
            cols = st.columns([1, 1, 4])
            if cols[0].button("Approve & merge", key=f"approve_{pr.number}", type="primary"):
                try:
                    approve_pr(pr.number)
                    st.success(f"Merged PR #{pr.number}")
                    st.rerun()
                except Exception as e:
                    st.error(f"merge failed: {e}")
            if cols[1].button("Reject", key=f"reject_{pr.number}"):
                if not reason.strip():
                    st.warning("Please provide a rejection reason — the reflector reads it.")
                else:
                    try:
                        rec = reject_reflector_pr(pr, reason)
                        if rec:
                            st.success(
                                f"Closed PR #{pr.number}; reflector won't re-propose "
                                f"`{rec['cluster_id']}` for 14d unless evidence doubles"
                            )
                        else:
                            st.success(f"Closed PR #{pr.number} (no metadata to record)")
                        st.rerun()
                    except Exception as e:
                        st.error(f"close failed: {e}")


if page == "Labeling Queue":
    _render_labeling_queue()
else:
    _render_pr_review()
