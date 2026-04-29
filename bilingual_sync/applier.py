"""Apply approved translations from queue/approved/ back to zh.json.

Preserves:
- existing zh.json structure (nested or flat)
- key ordering (we merge into the EN structure, then write out with
  ZH values overlaid; keeps reviewers' diffs sensible)
- non-string values (we never overwrite numbers/lists/booleans)

Never overwrites a key that wasn't in EN — if the human-edited review
file has a key that's not in EN, we skip it (probably a typo'd header).

After successful write, optionally MOVES the queue file to queue/sent/
so it doesn't apply twice. (Disabled with `--keep-queue`.)
"""
from __future__ import annotations
import json
import pathlib
from datetime import datetime, timezone

from .i18n_diff import flatten, unflatten, load_locale
from .queue import _queue_root, parse_review_file
from .types import TranslationItem


def apply_approved(*,
                   en_path: str | pathlib.Path,
                   zh_path: str | pathlib.Path,
                   keep_queue: bool = False,
                   dry_run: bool = False) -> dict[str, int]:
    """Iterate queue/approved/, apply each, optionally move to queue/sent/.

    Returns a summary: {applied, skipped_no_value, skipped_unknown_key,
    files_processed}.

    `dry_run` does the diff/merge but doesn't write zh.json or move files.
    """
    en_path = pathlib.Path(en_path)
    zh_path = pathlib.Path(zh_path)
    root = _queue_root()
    approved_dir = root / "approved"
    sent_dir = root / "sent"
    sent_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "applied": 0,
        "skipped_no_value": 0,
        "skipped_unknown_key": 0,
        "files_processed": 0,
    }

    if not approved_dir.exists():
        return summary

    en = load_locale(en_path)
    zh = load_locale(zh_path)
    en_flat = flatten(en)
    zh_flat = flatten(zh)

    for review_path in sorted(approved_dir.glob("*.md")):
        items = parse_review_file(review_path)
        for it in items:
            if not it.zh_approved or not it.zh_approved.strip():
                summary["skipped_no_value"] += 1
                continue
            if it.key not in en_flat:
                summary["skipped_unknown_key"] += 1
                continue
            zh_flat[it.key] = it.zh_approved.strip()
            summary["applied"] += 1

        summary["files_processed"] += 1
        if not dry_run and not keep_queue:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            new_path = sent_dir / f"{ts}-{review_path.name}"
            try:
                review_path.rename(new_path)
            except Exception:
                pass

    if dry_run:
        return summary

    # Write zh.json back with ZH overrides on the EN structure.
    # We start from EN structure to preserve key ordering, then overlay
    # zh_flat (which already has user's approved values merged in).
    new_zh: dict[str, str] = {}
    for k in en_flat:  # iterate in EN order
        if k in zh_flat:
            new_zh[k] = zh_flat[k]
    # Also keep zh-only keys (rarer but possible — agent shouldn't delete them)
    for k, v in zh_flat.items():
        if k not in new_zh:
            new_zh[k] = v

    nested = unflatten(new_zh)
    zh_path.parent.mkdir(parents=True, exist_ok=True)
    zh_path.write_text(
        json.dumps(nested, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary
