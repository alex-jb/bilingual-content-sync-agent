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
from datetime import datetime, timezone

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

4b. 2026-06-08 (Aidan Gomez citation pattern adapted): when a translation
    requires fabricating context the source doesn't carry (e.g. EN "Submit" is
    too generic — could be 提交/递交/发送 depending on flow), append
    `[src:none]` to flag that translation has 0 source-language grounding for
    register choice. HITL reviewer can then add tone_notes for that key.

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


TRANSLATION_SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "zh": {"type": "string"},
                },
                "required": ["key", "zh"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["translations"],
    "additionalProperties": False,
}


def translate_batch(items: list[TranslationItem],
                    *, model: str = DEFAULT_MODEL,
                    glossary: dict[str, str] | None = None,
                    tone_notes: str = "",
                    client: AnthropicClient | None = None) -> ReviewBundle:
    """Translate a list of items in one Claude call. Returns a ReviewBundle
    where each item.zh_proposed is set (or left empty on fallback).

    `client` is injectable for tests.

    v0.3: uses solo_founder_os.messages_create_json — guaranteed valid
    JSON output. Eliminates the markdown-fence-stripping +
    json.loads-with-fallback path that v0.2 had.
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

    data, err = client.messages_create_json(
        schema=TRANSLATION_SCHEMA,
        model=model,
        max_tokens=4000,
        system=system,
        messages=[{"role": "user", "content": user_payload}],
    )
    if err is not None:
        for it in bundle.items:
            it.notes = f"(LLM error, fill manually: {err})"
        bundle.raw_response = f"(error: {err})"
        try:
            from solo_founder_os import log_outcome
            log_outcome(".bilingual-content-sync-agent", task="translate_batch",
                        outcome="FAILED",
                        signal=f"messages_create_json error: {err}")
        except Exception:
            pass
        return bundle

    bundle.raw_response = json.dumps(data, ensure_ascii=False)
    translations = data.get("translations", [])
    by_key = {t.get("key"): t.get("zh", "") for t in translations
              if isinstance(t, dict)}
    # L3 skill library: bulk-record each translated key as an example.
    # Best-effort import — older solo-founder-os won't have skills module.
    try:
        from solo_founder_os import record_example
    except Exception:
        record_example = None  # type: ignore[assignment]
    n_missing = 0
    for it in bundle.items:
        proposed = by_key.get(it.key, "")
        if proposed:
            it.zh_proposed = proposed
            if record_example:
                try:
                    record_example(
                        "translate-en-to-zh",
                        inputs={
                            "key": it.key,
                            "en_value": it.en_value,
                            "context": it.context,
                        },
                        output=proposed,
                        note="Claude structured-output, pre-HITL",
                    )
                except Exception:
                    pass
        else:
            it.notes = "(LLM didn't return this key, fill manually)"
            n_missing += 1
    # Log a partial outcome if Claude skipped any keys — that means our
    # batch shape or schema isn't communicating clearly enough.
    if n_missing and n_missing >= max(1, len(bundle.items) // 4):
        try:
            from solo_founder_os import log_outcome
            log_outcome(".bilingual-content-sync-agent", task="translate_batch",
                        outcome="PARTIAL",
                        signal=(f"{n_missing}/{len(bundle.items)} keys missing "
                                "from LLM response"))
        except Exception:
            pass
    return bundle


def translate_via_batch_api(items: list[TranslationItem],
                             *, model: str = DEFAULT_MODEL,
                             glossary: dict[str, str] | None = None,
                             tone_notes: str = "",
                             chunk_size: int = BATCH_SIZE,
                             client: AnthropicClient | None = None,
                             poll_interval_s: float = 30.0,
                             timeout_s: float = 3600.0) -> ReviewBundle:
    """Translate a (large) list of items via Anthropic's Message Batches
    API — 50% off vs realtime, finishes in <1h typical.

    Use this for bulk one-shots like a full-catalog refresh of vibex's
    925 EN strings. For interactive ad-hoc translation, prefer
    translate_in_batches() (realtime).

    Returns the same ReviewBundle shape as translate_batch().

    `chunk_size` controls how many items per batch entry. With chunk_size=50,
    a 925-key catalog produces 19 batch entries. Each entry runs in
    parallel on Anthropic's side; total wall time is typically a few
    minutes regardless of total item count.
    """
    from solo_founder_os.batch import (
        batch_request, batch_submit, batch_wait,
    )

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

    # Chunk items, build one batch_request per chunk
    requests: list[dict] = []
    chunk_to_items: dict[str, list[TranslationItem]] = {}
    for i in range(0, len(bundle.items), chunk_size):
        chunk = bundle.items[i:i + chunk_size]
        cid = f"chunk-{i // chunk_size:04d}"
        chunk_to_items[cid] = chunk
        user_payload = _build_user_payload(chunk)
        requests.append(batch_request(
            custom_id=cid,
            model=model,
            max_tokens=4000,
            system=system,
            messages=[{"role": "user", "content": user_payload}],
            extra_headers={"anthropic-beta": "structured-outputs-2025-11-13"},
            output_config={"format": {"type": "json_schema",
                                       "schema": TRANSLATION_SCHEMA}},
        ))

    batch_id, err = batch_submit(client, requests)
    if err is not None:
        for it in bundle.items:
            it.notes = f"(batch submit failed: {err}, fill manually)"
        bundle.raw_response = f"(batch error: {err})"
        return bundle

    bundle.raw_response = f"(batch_id: {batch_id})"

    results, err = batch_wait(
        client, batch_id,
        poll_interval_s=poll_interval_s,
        timeout_s=timeout_s,
    )
    if err is not None:
        for it in bundle.items:
            it.notes = f"(batch wait failed: {err}, fill manually)"
        return bundle

    # Walk results — each chunk's content[0].text is JSON per the schema
    for cid, chunk_items in chunk_to_items.items():
        entry = (results or {}).get(cid)
        if not entry or "content" not in entry:
            err_msg = (entry or {}).get("error_message", "missing")
            for it in chunk_items:
                it.notes = f"(batch chunk failed: {err_msg}, fill manually)"
            continue
        try:
            text = "".join(b.get("text", "") for b in entry["content"]
                            if b.get("type") == "text").strip()
            data = json.loads(text)
            translations = data.get("translations", [])
        except Exception as e:
            for it in chunk_items:
                it.notes = f"(batch chunk parse error: {e}, fill manually)"
            continue
        by_key = {t.get("key"): t.get("zh", "") for t in translations
                   if isinstance(t, dict)}
        for it in chunk_items:
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
