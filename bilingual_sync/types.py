"""Core dataclasses passed between modules."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TranslationItem:
    """One key that needs (or has gotten) a ZH translation.

    `key` is dotted-path notation for nested JSON, e.g. "auth.login.button"
    points to en["auth"]["login"]["button"]. Flat keys ("save") work too.
    """
    key: str
    en_value: str
    zh_proposed: str = ""        # Claude's proposed ZH (or empty in template mode)
    zh_existing: str = ""        # what zh.json currently has (often empty for missing)
    zh_approved: Optional[str] = None  # what user approves; None until they edit
    context: str = ""            # surrounding context (sibling keys, etc.) for translator
    notes: str = ""              # any human note in the review file


@dataclass
class ReviewBundle:
    """A batch of TranslationItems shipped to the HITL queue as one markdown file."""
    items: list[TranslationItem] = field(default_factory=list)
    locale_pair: str = "en→zh"
    en_path: str = ""
    zh_path: str = ""
    drafted_at: Optional[datetime] = None
    raw_response: str = ""       # full LLM output for audit
