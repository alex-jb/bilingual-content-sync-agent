"""Diff EN locale against ZH locale — find what's missing in ZH.

Supports both flat ({"key": "val"}) and nested ({"section": {"key": "val"}})
JSON formats, transparently. Keys are flattened to dotted paths during
diff and unflattened when writing back.

A key is "missing in ZH" if ANY of:
  - key absent from zh
  - zh value is empty string
  - zh value equals the en value byte-for-byte (likely the EN was
    accidentally pasted into ZH — very common copy-mistake in i18n)
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Iterator

from .types import TranslationItem


def load_locale(path: str | Path) -> dict:
    """Load a locale JSON file. Returns empty dict if file missing."""
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def flatten(d: dict, *, sep: str = ".") -> dict[str, str]:
    """Flatten nested dict to {dotted.key: leaf_value}.

    Only string leaves are kept — non-string values (numbers, lists,
    booleans) are skipped because translation only applies to strings.
    """
    out: dict[str, str] = {}

    def _walk(obj: dict, prefix: str) -> None:
        for k, v in obj.items():
            key = f"{prefix}{sep}{k}" if prefix else k
            if isinstance(v, dict):
                _walk(v, key)
            elif isinstance(v, str):
                out[key] = v
            # else: skip — non-string leaves don't translate
    _walk(d, "")
    return out


def unflatten(flat: dict[str, str], *, sep: str = ".") -> dict:
    """Inverse of flatten. Rebuild nested dict from dotted keys."""
    out: dict = {}
    for k, v in flat.items():
        parts = k.split(sep)
        cur = out
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = v
    return out


def find_missing(en: dict, zh: dict, *,
                 max_context_siblings: int = 3) -> list[TranslationItem]:
    """Walk EN, return TranslationItems for every key missing in ZH.

    `context` field gets up to `max_context_siblings` neighboring EN
    values from the same section, joined by " | ". Helps Claude pick
    register-appropriate ZH (auth-flow buttons sound different from
    onboarding hero copy).
    """
    en_flat = flatten(en)
    zh_flat = flatten(zh)

    items: list[TranslationItem] = []
    for k, en_v in en_flat.items():
        existing = zh_flat.get(k, "")
        is_missing = (
            k not in zh_flat
            or not existing.strip()
            or existing.strip() == en_v.strip()  # english accidentally in zh
        )
        if not is_missing:
            continue

        # Sibling context: keys sharing the same parent path
        if "." in k:
            parent = k.rsplit(".", 1)[0]
            siblings = [v for kk, v in en_flat.items()
                        if kk != k
                        and kk.startswith(parent + ".")
                        and kk.count(".") == k.count(".")]
            ctx = " | ".join(siblings[:max_context_siblings])
        else:
            ctx = ""

        items.append(TranslationItem(
            key=k, en_value=en_v, zh_existing=existing, context=ctx,
        ))
    return items


def coverage_stats(en: dict, zh: dict) -> dict[str, int | float]:
    """Quick numbers for `bilingual-sync stats`."""
    en_flat = flatten(en)
    zh_flat = flatten(zh)
    missing = find_missing(en, zh)
    total = len(en_flat)
    covered = total - len(missing)
    pct = (covered / total * 100.0) if total else 0.0
    return {
        "total_keys": total,
        "covered_keys": covered,
        "missing_keys": len(missing),
        "coverage_pct": round(pct, 1),
        "zh_only_keys": len(set(zh_flat.keys()) - set(en_flat.keys())),
    }
