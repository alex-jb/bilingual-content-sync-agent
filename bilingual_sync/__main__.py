"""CLI entry — `python -m bilingual_sync <subcommand>`.

Subcommands:
    diff    Print a summary of missing keys (no LLM call)
    draft   Translate missing keys + write HITL review file
    apply   Apply queue/approved/*.md back to zh.json
    stats   Coverage report (covered / missing / orphaned)
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

from .applier import apply_approved
from .i18n_diff import coverage_stats, find_missing, load_locale
from .queue import write_review
from .translator import translate_in_batches
from .types import ReviewBundle


def _load_glossary(path: str | None) -> dict[str, str] | None:
    """Glossary file is JSON: {"forge": "锻造", "dojo": "道场"}."""
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def cmd_diff(args) -> int:
    en = load_locale(args.en)
    zh = load_locale(args.zh)
    missing = find_missing(en, zh)
    print(f"missing keys: {len(missing)}", file=sys.stderr)
    for it in missing[:20]:
        print(f"  - {it.key}: {it.en_value[:60]}", file=sys.stderr)
    if len(missing) > 20:
        print(f"  ... and {len(missing) - 20} more", file=sys.stderr)
    return 0


def cmd_stats(args) -> int:
    en = load_locale(args.en)
    zh = load_locale(args.zh)
    s = coverage_stats(en, zh)
    print(f"Total EN keys:    {s['total_keys']}")
    print(f"Covered in ZH:    {s['covered_keys']}  ({s['coverage_pct']}%)")
    print(f"Missing in ZH:    {s['missing_keys']}")
    print(f"ZH-only keys:     {s['zh_only_keys']}  (orphaned — EN no longer has them)")
    return 0


def cmd_draft(args) -> int:
    en = load_locale(args.en)
    zh = load_locale(args.zh)
    missing = find_missing(en, zh)
    if not missing:
        print("✓ no missing keys — locales in sync", file=sys.stderr)
        return 0

    glossary = _load_glossary(args.glossary)
    print(f"drafting translations for {len(missing)} key(s)…", file=sys.stderr)
    bundle = translate_in_batches(
        missing,
        glossary=glossary,
        tone_notes=args.tone or "",
    )
    bundle.locale_pair = "en→zh"
    bundle.en_path = str(args.en)
    bundle.zh_path = str(args.zh)
    path = write_review(bundle)
    print(f"\n📄 review: {path}", file=sys.stderr)
    print(f"   open in Obsidian, edit zh blocks, then move to queue/approved/",
          file=sys.stderr)
    print(f"   (run `bilingual-sync apply --en {args.en} --zh {args.zh}` to write back)",
          file=sys.stderr)
    return 0


def cmd_apply(args) -> int:
    summary = apply_approved(
        en_path=args.en, zh_path=args.zh,
        keep_queue=args.keep_queue, dry_run=args.dry_run,
    )
    print(f"applied:                {summary['applied']}", file=sys.stderr)
    print(f"skipped (no value):     {summary['skipped_no_value']}", file=sys.stderr)
    print(f"skipped (unknown key):  {summary['skipped_unknown_key']}", file=sys.stderr)
    print(f"queue files processed:  {summary['files_processed']}", file=sys.stderr)
    if args.dry_run:
        print("(dry-run — zh.json NOT written)", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    if os.getenv("BILINGUAL_SKIP") == "1":
        return 0

    p = argparse.ArgumentParser(
        prog="bilingual-content-sync-agent",
        description="Keep EN/ZH locale JSON in sync via Claude + HITL.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--en", required=True, help="path to en.json")
    common.add_argument("--zh", required=True, help="path to zh.json")

    s_diff = sub.add_parser("diff", parents=[common], help="Show missing keys")
    s_diff.set_defaults(func=cmd_diff)

    s_stats = sub.add_parser("stats", parents=[common], help="Coverage report")
    s_stats.set_defaults(func=cmd_stats)

    s_draft = sub.add_parser("draft", parents=[common],
                              help="Translate missing keys → HITL review file")
    s_draft.add_argument("--glossary", default=None,
                          help="Path to glossary JSON {en: zh}")
    s_draft.add_argument("--tone", default="indie SaaS, friendly, concise",
                          help="One-line tone description for the translator")
    s_draft.set_defaults(func=cmd_draft)

    s_apply = sub.add_parser("apply", parents=[common],
                              help="Write queue/approved/*.md back to zh.json")
    s_apply.add_argument("--keep-queue", action="store_true",
                          help="Don't move files to queue/sent/ after applying")
    s_apply.add_argument("--dry-run", action="store_true",
                          help="Show what would change but don't write zh.json")
    s_apply.set_defaults(func=cmd_apply)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
