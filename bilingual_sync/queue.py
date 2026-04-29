"""HITL queue — write a markdown review file, parse human-edited result.

Workflow:
  1. `bilingual-sync draft` writes queue/pending/<timestamp>-review.md
     with one section per missing translation: key, EN, proposed ZH, edit-line.
  2. Founder opens in Obsidian, edits ZH inline, MOVES file to queue/approved/.
  3. `bilingual-sync apply` reads queue/approved/*.md → writes back to zh.json.

Markdown format is hand-editable but parseable. Each item is delimited by
a `## key` header so the parser can chunk reliably.
"""
from __future__ import annotations
import os
import pathlib
import re
from datetime import datetime, timezone
from typing import Iterable

from .types import TranslationItem, ReviewBundle


def _queue_root() -> pathlib.Path:
    return pathlib.Path(os.getenv(
        "BILINGUAL_QUEUE",
        str(pathlib.Path.home() / ".bilingual-content-sync-agent" / "queue"),
    ))


# Header line for each item: "## <key>"
# The body is structured as labeled sections.
ITEM_TEMPLATE = """## {key}

- **EN:** {en}
- **Existing ZH:** {existing}
- **Context:** {context}

```zh
{proposed}
```
{notes_line}
"""


def _render_item(it: TranslationItem) -> str:
    notes_line = f"\n> {it.notes}\n" if it.notes else ""
    return ITEM_TEMPLATE.format(
        key=it.key,
        en=it.en_value,
        existing=it.zh_existing or "_(missing)_",
        context=it.context or "_(none)_",
        proposed=it.zh_proposed,
        notes_line=notes_line,
    )


def write_review(bundle: ReviewBundle, *,
                 status: str = "pending") -> pathlib.Path:
    """Write the bundle as one markdown file under queue/<status>/."""
    root = _queue_root() / status
    root.mkdir(parents=True, exist_ok=True)
    ts = (bundle.drafted_at or datetime.utcnow()).strftime("%Y%m%dT%H%M%S")
    path = root / f"{ts}-review.md"

    head = [
        "---",
        f"locale_pair: {bundle.locale_pair}",
        f"en_path: {bundle.en_path}",
        f"zh_path: {bundle.zh_path}",
        f"drafted_at: {bundle.drafted_at.isoformat() if bundle.drafted_at else ''}",
        f"n_items: {len(bundle.items)}",
        "---",
        "",
        f"# Translation Review · {len(bundle.items)} items · {bundle.locale_pair}",
        "",
        "**Workflow:**",
        "- Edit each `zh` block inline — that becomes the approved translation.",
        "- Delete a `## <key>` section to skip that key (won't be applied).",
        "- Move this file to `queue/approved/` to apply via `bilingual-sync apply`.",
        "- Move to `queue/rejected/` to archive without applying.",
        "",
    ]
    body = [_render_item(it) for it in bundle.items]
    path.write_text("\n".join(head) + "\n".join(body), encoding="utf-8")
    return path


def list_queue(*, status: str = "pending") -> list[pathlib.Path]:
    root = _queue_root() / status
    if not root.exists():
        return []
    return sorted(root.glob("*.md"))


# Regex to chunk by `## <key>` header. The key can contain dots, dashes,
# underscores, and word chars.
_HEADER_RE = re.compile(r"^## ([A-Za-z0-9_.\-]+)\s*$", re.MULTILINE)
# Inside each chunk: ```zh ... ``` block holds the approved ZH
_ZH_RE = re.compile(r"```zh\s*\n(.*?)\n```", re.DOTALL)


def parse_review_file(path: pathlib.Path) -> list[TranslationItem]:
    """Read a (possibly human-edited) review file. Return TranslationItems
    with `zh_approved` populated from the ```zh block.

    Rules:
    - A section's zh_approved equals the content of its ```zh ... ``` block,
      stripped. Empty block → zh_approved stays "".
    - Sections deleted by the user simply won't appear here.
    - Frontmatter and headers are ignored.
    """
    text = path.read_text(encoding="utf-8")

    # Find all `## <key>` positions to slice cleanly
    headers = list(_HEADER_RE.finditer(text))
    items: list[TranslationItem] = []
    for i, m in enumerate(headers):
        key = m.group(1)
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        chunk = text[start:end]
        zh_match = _ZH_RE.search(chunk)
        zh = zh_match.group(1).strip() if zh_match else ""
        # Try to recover EN from "**EN:** ..." line
        en_match = re.search(r"\*\*EN:\*\*\s*(.+)", chunk)
        en = en_match.group(1).strip() if en_match else ""
        items.append(TranslationItem(
            key=key, en_value=en,
            zh_proposed=zh,
            zh_approved=zh if zh else None,
        ))
    return items
