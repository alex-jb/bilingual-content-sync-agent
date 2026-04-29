"""Tests for queue.py + applier.py — end-to-end HITL roundtrip."""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bilingual_sync.types import TranslationItem, ReviewBundle
from bilingual_sync.queue import write_review, list_queue, parse_review_file
from bilingual_sync.applier import apply_approved


@pytest.fixture(autouse=True)
def _redirect_queue(tmp_path, monkeypatch):
    """Send queue to tmp so tests don't pollute ~/.bilingual-content-sync-agent/."""
    monkeypatch.setenv("BILINGUAL_QUEUE", str(tmp_path / "queue"))


def _bundle(items=None) -> ReviewBundle:
    return ReviewBundle(
        items=items or [
            TranslationItem(key="auth.login", en_value="Login",
                             zh_proposed="登录"),
        ],
        locale_pair="en→zh",
        en_path="/p/en.json",
        zh_path="/p/zh.json",
        drafted_at=datetime.now(timezone.utc),
    )


# ─── write_review + parse_review_file roundtrip ───────────────

def test_write_review_creates_pending_md(tmp_path, monkeypatch):
    monkeypatch.setenv("BILINGUAL_QUEUE", str(tmp_path / "queue"))
    path = write_review(_bundle())
    assert "pending" in str(path)
    assert path.exists()
    text = path.read_text()
    assert "## auth.login" in text
    assert "Login" in text
    assert "登录" in text
    assert "locale_pair: en→zh" in text


def test_parse_review_file_recovers_translations(tmp_path, monkeypatch):
    monkeypatch.setenv("BILINGUAL_QUEUE", str(tmp_path / "queue"))
    bundle = _bundle([
        TranslationItem(key="save", en_value="Save", zh_proposed="保存"),
        TranslationItem(key="cancel", en_value="Cancel", zh_proposed="取消"),
    ])
    path = write_review(bundle)
    parsed = parse_review_file(path)
    assert len(parsed) == 2
    by_key = {it.key: it for it in parsed}
    assert by_key["save"].zh_approved == "保存"
    assert by_key["cancel"].zh_approved == "取消"


def test_parse_handles_user_edits(tmp_path, monkeypatch):
    """Simulate a human editing the zh block before approving."""
    monkeypatch.setenv("BILINGUAL_QUEUE", str(tmp_path / "queue"))
    path = write_review(_bundle([
        TranslationItem(key="save", en_value="Save", zh_proposed="保存"),
    ]))
    text = path.read_text()
    # Human changes the proposed
    text = text.replace("保存", "保存草稿")  # better translation
    path.write_text(text)
    parsed = parse_review_file(path)
    assert parsed[0].zh_approved == "保存草稿"


def test_parse_handles_deleted_section(tmp_path, monkeypatch):
    """Human removes a section to skip that key."""
    monkeypatch.setenv("BILINGUAL_QUEUE", str(tmp_path / "queue"))
    path = write_review(_bundle([
        TranslationItem(key="save", en_value="Save", zh_proposed="保存"),
        TranslationItem(key="cancel", en_value="Cancel", zh_proposed="取消"),
    ]))
    text = path.read_text()
    # Drop the "cancel" section by truncating before its header
    text = text.split("## cancel")[0]
    path.write_text(text)
    parsed = parse_review_file(path)
    assert len(parsed) == 1
    assert parsed[0].key == "save"


def test_list_queue_per_status(tmp_path, monkeypatch):
    monkeypatch.setenv("BILINGUAL_QUEUE", str(tmp_path / "queue"))
    write_review(_bundle(), status="pending")
    write_review(_bundle(), status="approved")
    assert len(list_queue(status="pending")) == 1
    assert len(list_queue(status="approved")) == 1
    assert len(list_queue(status="rejected")) == 0


# ─── applier ───────────────────────────────────────────────

def test_apply_writes_back_to_zh_json(tmp_path, monkeypatch):
    monkeypatch.setenv("BILINGUAL_QUEUE", str(tmp_path / "queue"))
    en_path = tmp_path / "en.json"
    zh_path = tmp_path / "zh.json"
    en_path.write_text(json.dumps({"save": "Save", "cancel": "Cancel"}))
    zh_path.write_text(json.dumps({"save": "保存"}))  # cancel missing

    # Approved review with cancel = 取消
    bundle = _bundle([
        TranslationItem(key="cancel", en_value="Cancel", zh_proposed="取消"),
    ])
    write_review(bundle, status="approved")

    summary = apply_approved(en_path=en_path, zh_path=zh_path)
    assert summary["applied"] == 1

    written = json.loads(zh_path.read_text())
    assert written == {"save": "保存", "cancel": "取消"}


def test_apply_dry_run_does_not_write(tmp_path, monkeypatch):
    monkeypatch.setenv("BILINGUAL_QUEUE", str(tmp_path / "queue"))
    en_path = tmp_path / "en.json"
    zh_path = tmp_path / "zh.json"
    en_path.write_text(json.dumps({"save": "Save"}))
    zh_path.write_text(json.dumps({}))
    write_review(_bundle([
        TranslationItem(key="save", en_value="Save", zh_proposed="保存"),
    ]), status="approved")

    summary = apply_approved(en_path=en_path, zh_path=zh_path, dry_run=True)
    assert summary["applied"] == 1
    # zh.json untouched
    assert json.loads(zh_path.read_text()) == {}


def test_apply_skips_unknown_keys(tmp_path, monkeypatch):
    """If the human added a key that's not in EN, skip — don't pollute zh.json."""
    monkeypatch.setenv("BILINGUAL_QUEUE", str(tmp_path / "queue"))
    en_path = tmp_path / "en.json"
    zh_path = tmp_path / "zh.json"
    en_path.write_text(json.dumps({"save": "Save"}))
    zh_path.write_text(json.dumps({}))
    write_review(_bundle([
        TranslationItem(key="some_typo", en_value="X", zh_proposed="X"),
    ]), status="approved")

    summary = apply_approved(en_path=en_path, zh_path=zh_path)
    assert summary["skipped_unknown_key"] == 1
    assert summary["applied"] == 0


def test_apply_skips_empty_values(tmp_path, monkeypatch):
    monkeypatch.setenv("BILINGUAL_QUEUE", str(tmp_path / "queue"))
    en_path = tmp_path / "en.json"
    zh_path = tmp_path / "zh.json"
    en_path.write_text(json.dumps({"save": "Save"}))
    zh_path.write_text(json.dumps({}))
    write_review(_bundle([
        TranslationItem(key="save", en_value="Save", zh_proposed=""),
    ]), status="approved")
    summary = apply_approved(en_path=en_path, zh_path=zh_path)
    assert summary["skipped_no_value"] == 1


def test_apply_moves_files_to_sent(tmp_path, monkeypatch):
    monkeypatch.setenv("BILINGUAL_QUEUE", str(tmp_path / "queue"))
    en_path = tmp_path / "en.json"
    zh_path = tmp_path / "zh.json"
    en_path.write_text(json.dumps({"save": "Save"}))
    zh_path.write_text(json.dumps({}))
    write_review(_bundle([
        TranslationItem(key="save", en_value="Save", zh_proposed="保存"),
    ]), status="approved")

    apply_approved(en_path=en_path, zh_path=zh_path)
    approved_remaining = list((tmp_path / "queue" / "approved").glob("*.md"))
    sent_files = list((tmp_path / "queue" / "sent").glob("*.md"))
    assert len(approved_remaining) == 0
    assert len(sent_files) == 1


def test_apply_keep_queue_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("BILINGUAL_QUEUE", str(tmp_path / "queue"))
    en_path = tmp_path / "en.json"
    zh_path = tmp_path / "zh.json"
    en_path.write_text(json.dumps({"save": "Save"}))
    zh_path.write_text(json.dumps({}))
    write_review(_bundle([
        TranslationItem(key="save", en_value="Save", zh_proposed="保存"),
    ]), status="approved")

    apply_approved(en_path=en_path, zh_path=zh_path, keep_queue=True)
    approved_remaining = list((tmp_path / "queue" / "approved").glob("*.md"))
    assert len(approved_remaining) == 1


def test_apply_preserves_nested_structure(tmp_path, monkeypatch):
    monkeypatch.setenv("BILINGUAL_QUEUE", str(tmp_path / "queue"))
    en_path = tmp_path / "en.json"
    zh_path = tmp_path / "zh.json"
    en_path.write_text(json.dumps({
        "auth": {"login": "Login", "signup": "Sign up"},
    }))
    zh_path.write_text(json.dumps({"auth": {"login": "登录"}}))
    write_review(_bundle([
        TranslationItem(key="auth.signup", en_value="Sign up",
                         zh_proposed="注册"),
    ]), status="approved")

    apply_approved(en_path=en_path, zh_path=zh_path)
    written = json.loads(zh_path.read_text())
    assert written == {"auth": {"login": "登录", "signup": "注册"}}
