"""gh CLI wrappers for the PR-review page.

Every function shells out to `gh`. The functions are deliberately small so
tests can mock `subprocess.run` and assert the command shape rather than
hitting a real GitHub API.
"""

import json
import subprocess
from dataclasses import dataclass


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
