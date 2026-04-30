"""Tests for the bilingual-sync MCP server tools."""
from __future__ import annotations
import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

mcp_available = True
try:
    from mcp.server.fastmcp import FastMCP  # noqa: F401
except ImportError:
    mcp_available = False

pytestmark = pytest.mark.skipif(not mcp_available,
                                  reason="mcp optional dep not installed")


@pytest.fixture
def mod():
    from bilingual_sync import mcp_server
    return mcp_server


def _write_locales(tmp_path, en, zh):
    en_p = tmp_path / "en.json"
    zh_p = tmp_path / "zh.json"
    en_p.write_text(json.dumps(en, ensure_ascii=False), encoding="utf-8")
    zh_p.write_text(json.dumps(zh, ensure_ascii=False), encoding="utf-8")
    return str(en_p), str(zh_p)


def test_diff_locales_in_sync(mod, tmp_path):
    en_p, zh_p = _write_locales(tmp_path,
                                  {"hello": "Hello"},
                                  {"hello": "你好"})
    out = mod.diff_locales(en_p, zh_p)
    assert "Total EN keys: 1" in out
    assert "Missing in ZH: 0" in out


def test_diff_locales_with_missing(mod, tmp_path):
    en_p, zh_p = _write_locales(tmp_path,
                                  {"a": "Apple", "b": "Banana", "c": "Cherry"},
                                  {"a": "苹果"})
    out = mod.diff_locales(en_p, zh_p)
    assert "Missing in ZH: 2" in out
    assert "`b`" in out and "`c`" in out


def test_translate_missing_when_already_synced(mod, tmp_path):
    en_p, zh_p = _write_locales(tmp_path,
                                  {"hello": "Hello"},
                                  {"hello": "你好"})
    out = mod.translate_missing(en_p, zh_p)
    assert "no missing keys" in out


def test_apply_approved_no_queue(mod, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # queue dir resolves under cwd
    en_p, zh_p = _write_locales(tmp_path,
                                  {"hello": "Hello"},
                                  {})
    out = mod.apply_approved(en_p, zh_p)
    assert "No approved review files" in out


def test_main_skips_when_skip_env_set(mod, monkeypatch):
    monkeypatch.setenv("BILINGUAL_SYNC_SKIP", "1")
    with patch.object(mod.mcp, "run") as fake_run:
        mod.main()
    fake_run.assert_not_called()


def test_mcp_instance_is_fastmcp(mod):
    from mcp.server.fastmcp import FastMCP
    assert isinstance(mod.mcp, FastMCP)
