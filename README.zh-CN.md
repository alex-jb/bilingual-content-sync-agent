# bilingual-content-sync-agent

[English](README.md) | **中文**

> Solo Founder OS 第 4 个 agent —— 让 `en.json` 和 `zh.json`(或任何语言对)保持同步。Diff 找出缺的、Claude 翻译、写入 markdown HITL review 文件、批准后写回 locale JSON。**永远不自动写**。

[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/bilingual-content-sync-agent.svg)](https://pypi.org/project/bilingual-content-sync-agent/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](#)
[![Model](https://img.shields.io/badge/Claude-Sonnet_4.6-D97706?logoColor=white)](https://anthropic.com)

作者 [Alex Ji](https://github.com/alex-jb),为了 [VibeXForge](https://github.com/alex-jb/vibex) 的 925 条 EN/ZH i18n strings 而做。诞生于这一句:

> *每个新功能先上 English,中文晚几天到几周才补。哪些 key 过时了我得凌晨 1 点手动查。其他 11 个 maker 朋友也一样。*

## 它干什么

```
en.json + zh.json
        ↓
   diff(找出 EN 有,但 ZH 缺/空/被 EN 覆盖的 key)
        ↓
   Claude Sonnet 翻译(内置 vibex 风格术语表)
        ↓
   queue/pending/<时间戳>-review.md
        ↓
   你在 Obsidian 里改,改完移到 queue/approved/
        ↓
   apply → 写回 zh.json(保留嵌套 + key 顺序)
```

## CLI

```bash
# 覆盖率报告
bilingual-sync stats --en locales/en.json --zh locales/zh.json

# 看哪些 key 缺(不调 LLM)
bilingual-sync diff --en locales/en.json --zh locales/zh.json

# 翻译 + 写 review(调 LLM)
bilingual-sync draft \
  --en locales/en.json \
  --zh locales/zh.json \
  --glossary glossary.json \
  --tone "indie SaaS,氛围化,像素霓虹,P2P"

# 人工 review 完 → 文件移到 queue/approved/,然后:
bilingual-sync apply --en locales/en.json --zh locales/zh.json
```

## Glossary 文件

强制品牌词翻译一致。没有它 Claude 凭感觉选,跨次跑会漂移。

```json
{
  "Forge": "锻造",
  "Dojo": "道场",
  "Vibe": "氛围",
  "Login": "登录",
  "Sign up": "注册"
}
```

## 什么算"ZH 缺"

满足任一即缺:
- key 在 zh.json 里不存在
- ZH 值是空字符串
- ZH 值跟 EN 一字不差(常见的复制粘贴漏 —— 没工具基本看不出来)

## 设计取舍

- **HITL 是底线。** UI strings 每个用户每次 session 都看到。一条烂翻译全球上线 比 5 天补译时间糟太多。Agent 不在 explicit approve + apply 之前写 `zh.json`。
- **默认 Sonnet,不是 Haiku。** UI 翻译就是 Haiku 容易翻得太字面("Login" → "登入" 而不是"登录")的任务。925 条字符串 Sonnet 全跑下来 ~$0.50,差价值得。
- **批量调用。** 50 key/call 是 token 预算最甜的点。整个 vibex 库 ~20 次调用 ~$0.50。
- **保留 placeholder 和 HTML。** System prompt 明确禁止翻译 `{name}`、`<span>`、ICU 模板。如果 Claude 违反,review 文件会标记。
- **基于 solo-founder-os。** AnthropicClient 处理优雅降级 + 自动写 token usage 到 `~/.bilingual-content-sync-agent/usage.jsonl`(cost-audit-agent 月底自动汇总)。

## Roadmap

- [x] **v0.1** —— diff/draft/apply/stats CLI · HITL 队列 · Sonnet 翻译 · 43 tests · 优雅降级
- [ ] **v0.2** —— 多语言支持(EN→ES, EN→JA 等)—— 同一套代码,不同 glossary
- [ ] **v0.3** —— Watch 模式:commit 自动跑,把 stale key 写进 GitHub PR
- [ ] **v0.4** —— Context 预览:显示某 key 出现在哪个 React 组件
- [ ] **v0.5** —— 反向同步:检测 ZH-only 的孤儿 key(功能下线但 ZH 没删干净)

## MCP server(Claude Desktop / Cursor / Zed)

让 AI 助手直接帮你翻译缺失的 i18n 键。

```bash
pip install 'bilingual-content-sync-agent[mcp]'
```

```json
{
  "mcpServers": {
    "bilingual-sync": {
      "command": "bilingual-sync-mcp",
      "env": { "ANTHROPIC_API_KEY": "..." }
    }
  }
}
```

工具:`diff_locales(en, zh)` · `translate_missing(en, zh, ...)` · `apply_approved(en, zh)`

## 协议

MIT。
---

## 🧩 [Solo Founder OS](https://github.com/alex-jb/solo-founder-os) agent stack 的一员

一组共享 `solo-founder-os` 底座(Source/MetricSample 契约、HITL queue、AnthropicClient、notifiers、scheduler)的 MIT-licensed agents,逐渐在长。每个独立可用,组合起来覆盖单干创始人的全工作流。

| Agent | 干啥 |
|---|---|
| [solo-founder-os](https://github.com/alex-jb/solo-founder-os) | 共享底座(Source/MetricSample、AnthropicClient、HITL queue、notifiers、sfos-doctor / sfos-evolver / sfos-eval / sfos-retro / sfos-bus / sfos-inbox) |
| [build-quality-agent](https://github.com/alex-jb/build-quality-agent) | Pre-push diff 审查 + 本地 build runner — 在 push 前拦住会挂 CI 的改动 |
| [customer-discovery-agent](https://github.com/alex-jb/customer-discovery-agent) | Reddit 痛点抓取 + Claude 聚类做产品验证 |
| [funnel-analytics-agent](https://github.com/alex-jb/funnel-analytics-agent) | 每日 brief + 实时告警,跨 9 个 source(Vercel、GitHub、Supabase 等) |
| [vc-outreach-agent](https://github.com/alex-jb/vc-outreach-agent) | 投资人 cold email 起草 + HITL queue + SMTP 发送 |
| [cost-audit-agent](https://github.com/alex-jb/cost-audit-agent) | 月度账单审计跨 6 个 provider,标注美元 waste |
| [orallexa-marketing-agent](https://github.com/alex-jb/orallexa-marketing-agent) | 给 OSS 创业者用的 AI 营销 agent — 自动产出各平台专属营销稿 |

*每个 agent 自己的行在它自己 README 里被去掉。挑能解决你真问题的装。*
