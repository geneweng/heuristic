"""gh CLI wrappers for the PR-review page.

Every function shells out to `gh`. The functions are deliberately small so
tests can mock `subprocess.run` and assert the command shape rather than
hitting a real GitHub API.

`reject_reflector_pr` additionally writes the rejection to
`memory/rejections.jsonl` so the reflector's next run can avoid re-proposing
the same cluster (see #12 and skills/fraud-reflector/rejections.py).
"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pr_template import parse_metadata
from rejections import DEFAULT_REJECTIONS_LOG, append_rejection


REFLECTOR_TITLE_PREFIX = "reflector:"


@dataclass(frozen=True)
class ReflectorPR:
    number: int
    title: str
    body: str
    head_ref: str
    url: str


def _run_gh(args: list[str], *, runner=subprocess.run) -> str:
    result = runner(["gh", *args], check=True, capture_output=True, text=True)
    return result.stdout


def list_open_reflector_prs(*, runner=subprocess.run) -> list[ReflectorPR]:
    """Open PRs titled 'reflector: <scheme_id>'. Filter is done client-side so
    the function works without depending on labels having been applied."""
    raw = _run_gh(
        [
            "pr", "list", "--state", "open",
            "--json", "number,title,body,headRefName,url",
            "--limit", "50",
        ],
        runner=runner,
    )
    prs = json.loads(raw)
    return [
        ReflectorPR(
            number=p["number"],
            title=p["title"],
            body=p["body"],
            head_ref=p["headRefName"],
            url=p["url"],
        )
        for p in prs
        if p["title"].startswith(REFLECTOR_TITLE_PREFIX)
    ]


def get_pr_diff(pr_number: int, *, runner=subprocess.run) -> str:
    return _run_gh(["pr", "diff", str(pr_number)], runner=runner)


def approve_pr(pr_number: int, *, runner=subprocess.run) -> str:
    return _run_gh(["pr", "merge", str(pr_number), "--squash"], runner=runner)


def reject_pr(pr_number: int, reason: str, *, runner=subprocess.run) -> str:
    _run_gh(["pr", "comment", str(pr_number), "--body", reason], runner=runner)
    return _run_gh(["pr", "close", str(pr_number)], runner=runner)


def reject_reflector_pr(
    pr: ReflectorPR,
    reason: str,
    *,
    rejections_path: Path = DEFAULT_REJECTIONS_LOG,
    runner=subprocess.run,
) -> dict:
    """Reject a reflector PR and record the rejection for next-run feedback.

    Returns the rejection record written (or None if the PR body didn't carry
    the REFLECTOR_METADATA block, in which case only the close happens).
    """
    metadata = parse_metadata(pr.body)
    rejection_rec = None
    if metadata:
        rejection_rec = append_rejection(
            cluster_id=metadata["cluster_id"],
            scheme_id=metadata["scheme_id"],
            fn_count=int(metadata.get("fn_count", 0)),
            reason=reason,
            path=rejections_path,
        )
    reject_pr(pr.number, reason, runner=runner)
    return rejection_rec or {}
