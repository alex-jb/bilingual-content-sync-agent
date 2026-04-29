"""Tests for translator.py — system prompt builder + batch translate +
graceful degrade through solo-founder-os AnthropicClient."""
from __future__ import annotations
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bilingual_sync.translator import (
    build_system_prompt, translate_batch, translate_in_batches,
    _build_user_payload,
)
from bilingual_sync.types import TranslationItem
from solo_founder_os.anthropic_client import AnthropicClient
from solo_founder_os.testing import fake_anthropic, fake_anthropic_raises


def _client_with_fake(monkeypatch, fake_sdk_client) -> AnthropicClient:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    c = AnthropicClient(usage_log_path=None)
    c._client = fake_sdk_client
    return c


def _items(n: int = 2) -> list[TranslationItem]:
    return [
        TranslationItem(key=f"k{i}", en_value=f"value {i}", context=f"ctx{i}")
        for i in range(n)
    ]


# ─── build_system_prompt ─────────────────────────────────────

def test_system_prompt_includes_glossary():
    prompt = build_system_prompt(glossary={"forge": "锻造", "dojo": "道场"})
    assert "forge → 锻造" in prompt
    assert "dojo → 道场" in prompt


def test_system_prompt_includes_tone_notes():
    prompt = build_system_prompt(tone_notes="indie, gamified, neon-pixel")
    assert "indie, gamified, neon-pixel" in prompt


def test_system_prompt_works_without_options():
    prompt = build_system_prompt()
    assert "Glossary" not in prompt
    assert "Voice notes" not in prompt
    # But always has the core rules
    assert "STRICT JSON" in prompt


def test_system_prompt_warns_about_placeholders():
    """Critical rule — placeholder/HTML preservation."""
    prompt = build_system_prompt()
    assert "{name}" in prompt or "placeholder" in prompt.lower()


# ─── _build_user_payload ─────────────────────────────────────

def test_user_payload_includes_keys_and_context():
    items = [TranslationItem(key="auth.btn", en_value="Login",
                              context="signup | logout")]
    payload = _build_user_payload(items)
    assert "auth.btn" in payload
    assert "Login" in payload
    assert "signup | logout" in payload


# ─── translate_batch ────────────────────────────────────────

def test_translate_batch_empty_returns_empty_bundle():
    bundle = translate_batch([])
    assert bundle.items == []


def test_translate_batch_no_api_key_marks_items(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    items = _items(2)
    bundle = translate_batch(items)
    for it in bundle.items:
        assert it.zh_proposed == ""
        assert "no ANTHROPIC_API_KEY" in it.notes


def test_translate_batch_parses_strict_json(monkeypatch):
    fake = fake_anthropic(json.dumps({
        "translations": [
            {"key": "k0", "zh": "值零"},
            {"key": "k1", "zh": "值一"},
        ]
    }))
    client = _client_with_fake(monkeypatch, fake)
    bundle = translate_batch(_items(2), client=client)
    by_key = {it.key: it for it in bundle.items}
    assert by_key["k0"].zh_proposed == "值零"
    assert by_key["k1"].zh_proposed == "值一"


def test_translate_batch_strips_markdown_fence(monkeypatch):
    fake = fake_anthropic(
        '```json\n{"translations":[{"key":"k0","zh":"v0"}]}\n```'
    )
    client = _client_with_fake(monkeypatch, fake)
    bundle = translate_batch(_items(1), client=client)
    assert bundle.items[0].zh_proposed == "v0"


def test_translate_batch_unparseable_marks_items(monkeypatch):
    fake = fake_anthropic("not even json")
    client = _client_with_fake(monkeypatch, fake)
    bundle = translate_batch(_items(2), client=client)
    for it in bundle.items:
        assert it.zh_proposed == ""
        assert "unparseable" in it.notes


def test_translate_batch_exception_marks_items(monkeypatch):
    fake = fake_anthropic_raises(Exception("rate limit"))
    client = _client_with_fake(monkeypatch, fake)
    bundle = translate_batch(_items(2), client=client)
    for it in bundle.items:
        assert "rate limit" in it.notes
        assert it.zh_proposed == ""


def test_translate_batch_missing_key_in_response_marks_item(monkeypatch):
    """LLM returned only k0 but we asked for k0 + k1."""
    fake = fake_anthropic(json.dumps({
        "translations": [{"key": "k0", "zh": "ok"}]
    }))
    client = _client_with_fake(monkeypatch, fake)
    bundle = translate_batch(_items(2), client=client)
    by_key = {it.key: it for it in bundle.items}
    assert by_key["k0"].zh_proposed == "ok"
    assert by_key["k1"].zh_proposed == ""
    assert "didn't return" in by_key["k1"].notes


# ─── translate_in_batches ───────────────────────────────────

def test_in_batches_chunks_large_lists(monkeypatch):
    """120 items, batch_size=50 → 3 calls, all merged into one bundle."""
    fake = fake_anthropic(json.dumps({"translations": []}))
    client = _client_with_fake(monkeypatch, fake)
    bundle = translate_in_batches(_items(120), batch_size=50, client=client)
    assert len(bundle.items) == 120
    # The mock recorded 3 calls
    assert fake.messages.create.call_count == 3


def test_in_batches_small_list_no_chunking(monkeypatch):
    fake = fake_anthropic(json.dumps({"translations": []}))
    client = _client_with_fake(monkeypatch, fake)
    translate_in_batches(_items(3), batch_size=50, client=client)
    assert fake.messages.create.call_count == 1
