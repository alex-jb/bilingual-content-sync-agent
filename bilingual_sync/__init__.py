"""bilingual-content-sync-agent — keep EN/ZH locale JSON in sync via Claude + HITL.

Solo Founder OS agent #4 (Tier 2). Built specifically for VibeXForge's
925 EN/ZH i18n strings — every new feature ships English first, ZH
catches up days/weeks later, and tracking which keys are stale is manual
labor.

This agent:
  1. Diffs en.json against zh.json — finds keys present in EN but
     missing/empty/stale in ZH.
  2. Calls Claude (Sonnet by default — translation needs nuance) to
     propose ZH for each missing key, primed with vibex's tone vocabulary
     (forge / dojo / vibe / dojo, etc).
  3. Writes proposals to a markdown HITL review file. Founder reviews in
     Obsidian, edits inline, moves to approved/.
  4. `apply` reads approved files and writes the approved values back
     to zh.json, preserving structure + key ordering.

NEVER auto-writes to zh.json without human approval.

Built on solo-founder-os: AnthropicClient (auto cost log → cost-audit),
HITL markdown queue (mirrors vc-outreach-agent pattern).
"""
__version__ = "0.4.0"

from .types import TranslationItem, ReviewBundle
from .i18n_diff import load_locale, find_missing, flatten, unflatten
from .translator import translate_batch
from .queue import write_review, list_queue, parse_review_file
from .applier import apply_approved

__all__ = [
    "TranslationItem", "ReviewBundle",
    "load_locale", "find_missing", "flatten", "unflatten",
    "translate_batch",
    "write_review", "list_queue", "parse_review_file",
    "apply_approved",
]
