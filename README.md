# bilingual-content-sync-agent

**English** | [中文](README.zh-CN.md)

> Solo Founder OS agent #4 — keep `en.json` and `zh.json` (or any locale pair) in sync. Diffs, translates missing keys via Claude, queues them in a markdown HITL review file, applies approved edits back to your locale JSON. Never auto-writes without human approval.

[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/bilingual-content-sync-agent.svg)](https://pypi.org/project/bilingual-content-sync-agent/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](#)
[![Model](https://img.shields.io/badge/Claude-Sonnet_4.6-D97706?logoColor=white)](https://anthropic.com)

Built by [Alex Ji](https://github.com/alex-jb) for [VibeXForge](https://github.com/alex-jb/vibex)'s 925 EN/ZH i18n strings. Born from this thought:

> *Every feature ships English first. ZH catches up days or weeks later. Tracking which keys are stale is manual labor I do at 1 AM. Same for the next 11 makers I know.*

## What it does

```
en.json + zh.json
        ↓
   diff (find keys present in EN, missing/empty/echo'd in ZH)
        ↓
   translate via Claude Sonnet (vibex-tone glossary baked in)
        ↓
   queue/pending/<timestamp>-review.md
        ↓
   founder edits in Obsidian, moves to queue/approved/
        ↓
   apply → writes back to zh.json (preserves nesting + key order)
```

## CLI

```bash
# Coverage report
bilingual-sync stats --en locales/en.json --zh locales/zh.json

# Show what's missing (no LLM call)
bilingual-sync diff --en locales/en.json --zh locales/zh.json

# Translate + write review file (LLM call)
bilingual-sync draft \
  --en locales/en.json \
  --zh locales/zh.json \
  --glossary glossary.json \
  --tone "indie SaaS, gamified, neon-pixel, peer-to-peer"

# After human review → move file to queue/approved/, then:
bilingual-sync apply --en locales/en.json --zh locales/zh.json
```

## Glossary file

Glossary keys force consistent translation of brand terms. Without it, Claude picks reasonable defaults but those drift across runs.

```json
{
  "Forge": "锻造",
  "Dojo": "道场",
  "Vibe": "氛围",
  "Login": "登录",
  "Sign up": "注册"
}
```

## What gets flagged as "missing"

A key is missing in ZH when ANY of:
- key absent from `zh.json`
- ZH value is empty string
- ZH value byte-equals the EN value (a common copy-paste mistake — easy to miss without tooling)

## Design choices

- **HITL is non-negotiable.** UI strings are seen by every user every session. One bad translation that ships globally is worse than five days of catch-up. The agent never writes to `zh.json` without an explicit approve-and-apply step.
- **Sonnet by default, not Haiku.** Cold UI translations are exactly the task where naïve Haiku output gets too literal ("Login" → "登入" instead of "登录"). Sonnet's nuance is worth the 3× cost for 925 strings (~$0.50 total).
- **Batched calls.** 50 keys per call is the token-budget sweet spot. Full vibex catalog = ~20 calls = ~$0.50.
- **Preserves placeholders + HTML.** The system prompt explicitly forbids translating `{name}`, `<span>`, ICU patterns. If Claude breaks this it gets flagged in the review file.
- **Built on solo-founder-os.** AnthropicClient handles graceful degrade + auto-logs token usage to `~/.bilingual-content-sync-agent/usage.jsonl` (cost-audit-agent picks it up monthly).

## Roadmap

- [x] **v0.1** — diff/draft/apply/stats CLI · HITL queue · Sonnet drafting · 43 tests · graceful degrade
- [ ] **v0.2** — Multi-language support (EN→ES, EN→JA, etc.) — same code path, different glossaries
- [ ] **v0.3** — Watch mode: re-run on commit, post-flagging stale keys to GitHub PR
- [ ] **v0.4** — In-context preview: show the React component a key appears in
- [ ] **v0.5** — Reverse sync: detect ZH-only orphan keys (features that got removed but ZH was forgotten)

## License

MIT.
