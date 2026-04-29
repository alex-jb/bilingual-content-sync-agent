"""Translate batches of EN i18n strings to ZH via Claude.

Why Sonnet by default: i18n translation is the kind of task where naïve
Haiku output gets too literal ("login" → "登入" instead of "登录").
Sonnet's grasp of register + tone matches what makers actually want
their app to sound like.

Why batches: one API call per key would waste tokens (system prompt
overhead × N) and clobber rate limits. Batching 50 keys per call gets
the cost down to ~$0.005 for a full vibex catalog refresh.

Fallback path: if no ANTHROPIC_API_KEY, we return TranslationItems with
zh_proposed left empty and `notes` set to "(no key — fill manually)".
The HITL review file still works; user just types each ZH directly.
"""
from __future__ import annotations
import json
import os
import pathlib
import re
from datetime import datetime, timezone
from typing import Iterable

from solo_founder_os.anthropic_client import (
    AnthropicClient,
    DEFAULT_SONNET_MODEL,
)

from .types import TranslationItem, ReviewBundle


DEFAULT_MODEL = os.getenv("BILINGUAL_TRANSLATE_MODEL", DEFAULT_SONNET_MODEL)
USAGE_LOG_PATH = (pathlib.Path.home()
                  / ".bilingual-content-sync-agent" / "usage.jsonl")
BATCH_SIZE = int(os.getenv("BILINGUAL_BATCH_SIZE", "50"))


def build_system_prompt(*, glossary: dict[str, str] | None = None,
                        tone_notes: str = "") -> str:
    """Compose the translator's system prompt.

    `glossary` is a dict of EN→ZH terms that MUST be used consistently
    (e.g. for vibex: {"forge": "锻造", "dojo": "道场"}). When empty,
    Claude picks reasonable defaults but those drift across runs.

    `tone_notes` is freeform — describe the product voice. For vibex:
    "indie, gamified, neon-pixel, peer-to-peer". This goes verbatim into
    the prompt so the model can pattern-match the register.
    """
    base = """You are a UI string translator from English to Simplified Chinese for an indie SaaS product.

Rules — break any of these and the translation will be rejected by HITL:

1. Match the product's tone. The voice notes below describe how this app talks to its users; mirror that register.

2. UI strings, not literature. Buttons stay imperative + short ("Save" → "保存", not "请保存"). Headings are punchy. Error messages are direct.

3. Preserve all placeholders, ICU/MessageFormat patterns, and HTML tags exactly. `Hello {name}!` → `你好,{name}!` (DON'T translate {name}).

4. Never invent meaning. If the EN is genuinely ambiguous, output the most likely interpretation and add a `(?)` at the end of zh_proposed so HITL flags it.

5. Use the glossary below for any term that appears. Consistency across the app matters more than translating each occurrence creatively.

6. Output STRICT JSON of shape:
   {"translations": [{"key": "<exact-key-from-input>", "zh": "<chinese>"}, ...]}
   No preamble, no markdown fences, no comments.

"""
    if tone_notes:
        base += f"\nVoice notes: {tone_notes}\n"
    if glossary:
        base += "\nGlossary (use exactly these for these terms):\n"
        for en, zh in glossary.items():
            base += f"  - {en} → {zh}\n"
    return base


def _build_user_payload(items: list[TranslationItem]) -> str:
    """Render the batch as a structured input."""
    lines = ["Translate each EN string to ZH. Use the `context` field for register cues.\n"]
    payload = {"items": [
        {
            "key": it.key,
            "en": it.en_value,
            "context": it.context or None,
            "zh_existing": it.zh_existing or None,
        }
        for it in items
    ]}
    lines.append(json.dumps(payload, ensure_ascii=False, indent=2))
    return "\n".join(lines)


def translate_batch(items: list[TranslationItem],
                    *, model: str = DEFAULT_MODEL,
                    glossary: dict[str, str] | None = None,
                    tone_notes: str = "",
                    client: AnthropicClient | None = None) -> ReviewBundle:
    """Translate a list of items in one Claude call. Returns a ReviewBundle
    where each item.zh_proposed is set (or left empty on fallback).

    `client` is injectable for tests.
    """
    bundle = ReviewBundle(items=list(items),
                          drafted_at=datetime.now(timezone.utc))
    if not items:
        return bundle

    if client is None:
        client = AnthropicClient(usage_log_path=USAGE_LOG_PATH)

    if not client.configured:
        for it in bundle.items:
            it.notes = "(no ANTHROPIC_API_KEY — fill manually)"
        bundle.raw_response = "(template mode — no API key)"
        return bundle

    system = build_system_prompt(glossary=glossary, tone_notes=tone_notes)
    user_payload = _build_user_payload(bundle.items)

    resp, err = client.messages_create(
        model=model,
        max_tokens=4000,
        system=system,
        messages=[{"role": "user", "content": user_payload}],
    )
    if err is not None:
        for it in bundle.items:
            it.notes = f"(LLM error, fill manually: {err})"
        bundle.raw_response = f"(error: {err})"
        return bundle

    text = AnthropicClient.extract_text(resp)
    bundle.raw_response = text

    # Strip ```json fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned).strip()

    try:
        data = json.loads(cleaned)
        translations = data.get("translations", [])
    except Exception:
        for it in bundle.items:
            it.notes = "(unparseable LLM response, fill manually)"
        return bundle

    by_key = {t.get("key"): t.get("zh", "") for t in translations
              if isinstance(t, dict)}
    for it in bundle.items:
        proposed = by_key.get(it.key, "")
        if proposed:
            it.zh_proposed = proposed
        else:
            it.notes = "(LLM didn't return this key, fill manually)"
    return bundle


def translate_in_batches(items: list[TranslationItem],
                          *, batch_size: int = BATCH_SIZE,
                          **kwargs) -> ReviewBundle:
    """Translate large lists by chunking into BATCH_SIZE calls. Returns
    one merged ReviewBundle with all items."""
    if len(items) <= batch_size:
        return translate_batch(items, **kwargs)

    merged = ReviewBundle(items=[],
                          drafted_at=datetime.now(timezone.utc))
    for i in range(0, len(items), batch_size):
        chunk = items[i:i + batch_size]
        b = translate_batch(chunk, **kwargs)
        merged.items.extend(b.items)
        # Keep just the last raw_response — full chain bloats the queue file
    return merged
