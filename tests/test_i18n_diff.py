"""Tests for i18n_diff — flatten/unflatten + find_missing + coverage_stats."""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bilingual_sync.i18n_diff import (
    flatten, unflatten, find_missing, coverage_stats, load_locale,
)


# ─── flatten / unflatten ─────────────────────────────────────

def test_flatten_flat_dict():
    assert flatten({"a": "x", "b": "y"}) == {"a": "x", "b": "y"}


def test_flatten_nested():
    out = flatten({"auth": {"login": {"button": "Login"}}})
    assert out == {"auth.login.button": "Login"}


def test_flatten_skips_non_strings():
    """Numbers, lists, booleans don't translate — drop them."""
    out = flatten({"a": "yes", "b": 42, "c": [1, 2], "d": True})
    assert out == {"a": "yes"}


def test_unflatten_round_trip():
    original = {"a": {"b": "1", "c": {"d": "2"}}, "e": "3"}
    flat = flatten(original)
    rebuilt = unflatten(flat)
    assert rebuilt == original


def test_unflatten_handles_flat_keys():
    assert unflatten({"a": "x", "b": "y"}) == {"a": "x", "b": "y"}


# ─── find_missing ────────────────────────────────────────────

def test_find_missing_simple():
    en = {"save": "Save", "cancel": "Cancel"}
    zh = {"save": "保存"}
    items = find_missing(en, zh)
    assert len(items) == 1
    assert items[0].key == "cancel"
    assert items[0].en_value == "Cancel"


def test_find_missing_treats_empty_zh_as_missing():
    en = {"save": "Save"}
    zh = {"save": ""}
    items = find_missing(en, zh)
    assert len(items) == 1
    assert items[0].zh_existing == ""


def test_find_missing_treats_en_in_zh_as_missing():
    """A common copy-paste mistake — EN value pasted into zh.json."""
    en = {"save": "Save"}
    zh = {"save": "Save"}  # English in zh
    items = find_missing(en, zh)
    assert len(items) == 1


def test_find_missing_empty_when_zh_complete():
    en = {"a": "X", "b": "Y"}
    zh = {"a": "甲", "b": "乙"}
    assert find_missing(en, zh) == []


def test_find_missing_with_nested():
    en = {"auth": {"login": "Login", "signup": "Sign up"}}
    zh = {"auth": {"login": "登录"}}
    items = find_missing(en, zh)
    assert len(items) == 1
    assert items[0].key == "auth.signup"


def test_find_missing_includes_sibling_context():
    en = {
        "auth": {
            "login_button": "Login",
            "signup_button": "Sign up",
            "reset_button": "Reset password",
        },
    }
    zh = {"auth": {"login_button": "登录"}}
    items = find_missing(en, zh)
    # The two missing keys should each have the OTHER missing's siblings
    # in their context (EN siblings, not ZH)
    by_key = {it.key: it for it in items}
    sig = by_key["auth.signup_button"]
    assert "Login" in sig.context  # sibling EN string
    assert "Reset password" in sig.context


# ─── coverage_stats ──────────────────────────────────────────

def test_coverage_stats_full():
    en = {"a": "x", "b": "y"}
    zh = {"a": "甲", "b": "乙"}
    s = coverage_stats(en, zh)
    assert s["total_keys"] == 2
    assert s["covered_keys"] == 2
    assert s["coverage_pct"] == 100.0
    assert s["missing_keys"] == 0


def test_coverage_stats_partial():
    en = {"a": "x", "b": "y", "c": "z"}
    zh = {"a": "甲"}
    s = coverage_stats(en, zh)
    assert s["covered_keys"] == 1
    assert s["missing_keys"] == 2
    assert round(s["coverage_pct"], 1) == 33.3


def test_coverage_stats_orphaned_zh():
    """Keys in ZH but no longer in EN."""
    en = {"a": "x"}
    zh = {"a": "甲", "removed_feature": "废"}
    s = coverage_stats(en, zh)
    assert s["zh_only_keys"] == 1


def test_coverage_stats_empty():
    assert coverage_stats({}, {})["total_keys"] == 0


# ─── load_locale ─────────────────────────────────────────────

def test_load_locale_returns_empty_for_missing(tmp_path):
    assert load_locale(tmp_path / "absent.json") == {}


def test_load_locale_reads_json(tmp_path):
    p = tmp_path / "en.json"
    p.write_text(json.dumps({"a": "X"}), encoding="utf-8")
    assert load_locale(p) == {"a": "X"}
