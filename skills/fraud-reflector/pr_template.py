"""Render reflector PR bodies and parse the metadata block back out.

The template lives at `.github/PULL_REQUEST_TEMPLATE/reflector.md` so GitHub's
UI also picks it up if someone opens a reflector PR by hand. We render the
same file ourselves for `gh pr create --body` since gh doesn't apply templates
to programmatic creates.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = REPO_ROOT / ".github" / "PULL_REQUEST_TEMPLATE" / "reflector.md"

_METADATA_RE = re.compile(
    r"<!--\s*REFLECTOR_METADATA\s*(?P<json>\{.*?\})\s*-->",
    re.DOTALL,
)


def render_body(
    *,
    scheme_id: str,
    confidence: float,
    description: str,
    rationale: str,
    cluster_id: str,
    fn_count: int,
    cited_txn_ids: list[str],
    created_at: str,
    extra_metadata: dict | None = None,
) -> str:
    """Render reflector PR body. Embeds a machine-parseable metadata block."""
    cited_csv = ", ".join(f"`{c}`" for c in cited_txn_ids) or "_(none)_"
    metadata = {
        "scheme_id": scheme_id,
        "cluster_id": cluster_id,
        "fn_count": fn_count,
        "cited_txn_ids": cited_txn_ids,
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    return TEMPLATE_PATH.read_text().format(
        scheme_id=scheme_id,
        confidence=confidence,
        description=description,
        rationale=rationale,
        cluster_id=cluster_id,
        fn_count=fn_count,
        cited_csv=cited_csv,
        created_at=created_at,
        metadata_json=json.dumps(metadata),
    )


def parse_metadata(body: str) -> dict | None:
    """Extract the REFLECTOR_METADATA block, if any. Returns None if absent."""
    m = _METADATA_RE.search(body or "")
    if not m:
        return None
    try:
        return json.loads(m.group("json"))
    except json.JSONDecodeError:
        return None
