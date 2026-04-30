"""MCP server — let Claude Desktop / Cursor / Zed translate i18n keys.

Useful when you've added new EN strings to your locale file and want to
ask Claude "translate the missing keys" without wiring up the CLI.

Tools:
  - diff_locales(en_path, zh_path)
        Coverage stats + list of missing keys (no LLM call).
  - translate_missing(en_path, zh_path, glossary_json=None, tone_notes=None,
                       use_batch_api=False)
        Translate the missing keys, return ReviewBundle as markdown.
  - apply_approved(en_path, zh_path)
        Apply queue/approved/*.md back to zh.json.

Install:
    pip install bilingual-content-sync-agent[mcp]

Wire to Claude Desktop:

    {
      "mcpServers": {
        "bilingual-sync": {
          "command": "bilingual-sync-mcp",
          "env": { "ANTHROPIC_API_KEY": "..." }
        }
      }
    }
"""
from __future__ import annotations
import json
import os
import sys

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    print("bilingual-sync-mcp requires the `mcp` package. "
          "Install with: pip install 'bilingual-content-sync-agent[mcp]'",
          file=sys.stderr)
    raise SystemExit(1) from e

from .applier import apply_approved as _apply_approved
from .i18n_diff import coverage_stats, find_missing, load_locale
from .queue import write_review
from .translator import translate_in_batches, translate_via_batch_api


mcp = FastMCP("bilingual-sync")


@mcp.tool()
def diff_locales(en_path: str, zh_path: str) -> str:
    """Diff two locale JSON files. No LLM call — fast and free.

    Returns coverage stats (covered / missing / orphaned) plus the first
    20 missing keys.
    """
    en = load_locale(en_path)
    zh = load_locale(zh_path)
    s = coverage_stats(en, zh)
    missing = find_missing(en, zh)
    out = [
        f"## Coverage",
        f"- Total EN keys: {s['total_keys']}",
        f"- Covered in ZH: {s['covered_keys']} ({s['coverage_pct']}%)",
        f"- Missing in ZH: {s['missing_keys']}",
        f"- Orphan ZH-only: {s['zh_only_keys']}",
    ]
    if missing:
        out.extend(["", "## First 20 missing"])
        for it in missing[:20]:
            out.append(f"- `{it.key}` — {it.en_value[:80]}")
        if len(missing) > 20:
            out.append(f"- _… and {len(missing) - 20} more_")
    return "\n".join(out)


@mcp.tool()
def translate_missing(
    en_path: str,
    zh_path: str,
    glossary_json: str = "",
    tone_notes: str = "",
    use_batch_api: bool = False,
) -> str:
    """Translate the keys missing from zh.json. Writes a review bundle to
    the HITL queue (queue/pending/) for human approval before apply.

    Args:
        en_path, zh_path: locale file paths.
        glossary_json: optional JSON string mapping EN→ZH for stable
                       brand terms, e.g. '{"forge": "锻造"}'.
        tone_notes: optional voice note, e.g. "indie, gamified, neon".
        use_batch_api: if True, submit through Anthropic Message Batches
                       API (50% off, async, ~1h SLA). Best for full-catalog
                       refreshes; bad for the iterate-and-apply loop.

    Returns: HITL review file path + first ~10 translation samples.
    """
    en = load_locale(en_path)
    zh = load_locale(zh_path)
    missing = find_missing(en, zh)
    if not missing:
        return "✓ no missing keys — locales already in sync."

    glossary = json.loads(glossary_json) if glossary_json.strip() else None
    if use_batch_api:
        bundle = translate_via_batch_api(missing, glossary=glossary,
                                           tone_notes=tone_notes or "")
    else:
        bundle = translate_in_batches(missing, glossary=glossary,
                                        tone_notes=tone_notes or "")
    bundle.locale_pair = "en→zh"
    bundle.en_path = str(en_path)
    bundle.zh_path = str(zh_path)
    path = write_review(bundle)

    out = [f"📄 review file: `{path}`",
           f"   Translated {len(bundle.items)} key(s).",
           "",
           "## First samples"]
    for it in bundle.items[:10]:
        out.append(f"- `{it.key}` — {it.en_value[:60]} → {it.zh_proposed[:60]}")
        if it.notes:
            out.append(f"  _note: {it.notes[:100]}_")
    out.append("")
    out.append("Open in Obsidian, edit zh blocks, move to queue/approved/, "
                 "then call apply_approved.")
    return "\n".join(out)


@mcp.tool()
def apply_approved(en_path: str, zh_path: str, dry_run: bool = False) -> str:
    """Apply queue/approved/*.md edits back to zh.json.

    Args:
        en_path, zh_path: locale file paths.
        dry_run: if True, compute the merge but don't touch disk.
    """
    summary = _apply_approved(en_path=en_path, zh_path=zh_path,
                                dry_run=dry_run)
    if summary["files_processed"] == 0:
        return "No approved review files in queue/approved/ to apply."
    parts = [
        f"✓ Processed {summary['files_processed']} review file(s).",
        f"   Applied: {summary['applied']} key(s).",
    ]
    if summary["skipped_no_value"]:
        parts.append(f"   Skipped (no zh value): {summary['skipped_no_value']}")
    if summary["skipped_unknown_key"]:
        parts.append(f"   Skipped (unknown key): {summary['skipped_unknown_key']}")
    if dry_run:
        parts.append("   _(dry run — no files written)_")
    else:
        parts.append(f"   {zh_path} updated · review files moved to queue/sent/.")
    return "\n".join(parts)


def main() -> None:
    """Console-script entry point. Runs the MCP server over stdio."""
    if os.getenv("BILINGUAL_SYNC_SKIP") == "1":
        return
    mcp.run()


if __name__ == "__main__":
    main()
