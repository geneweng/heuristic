---
name: analyst-ui
description: Streamlit UI for the analyst persona — label flagged txns, review reflector PRs
---

# analyst-ui

Local-only Streamlit app for the analyst persona. Two pages:

1. **Labeling Queue** — pulls flagged txns (`decision in {review, block}`) from
   `runs/*.jsonl` that don't yet appear in `labels/labels.jsonl`. Analyst marks
   each as fraud / legit / unsure, leaves a free-text note. Submit appends to
   the labels file. The reflector reads those notes — they end up cited in
   proposed rules.

2. **PR Review** — lists open reflector-authored PRs via `gh pr list`, shows
   each one's docstring + diff + cited evidence. Approve calls
   `gh pr merge --squash`; reject calls `gh pr close --comment`.

Per #8 AC: no auth — POC only, run on localhost via `make ui`.

## Layout

- `app.py`        — Streamlit entry (thin)
- `queue.py`      — build_queue() (pure, testable)
- `labels_io.py`  — append_label / load_labels (pure, testable)
- `pr_review.py`  — gh-CLI wrappers (subprocess; mockable)

## Run

```bash
make ui
# opens http://localhost:8501
```
