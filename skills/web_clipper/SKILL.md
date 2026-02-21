---
name: web_clipper
description: 即时 URL 剪报工具。输入一个网页 URL，自动完成：正文提取（trafilatura）→ Bouncer LLM 评分 → 高分写入 Obsidian Inbox（status: pending）→ Telegram 通知。区别于 cognitive_bouncer 的 cron 模式，web_clipper 是实时触发的单文章精读入口。激活条件：用户说 "clip <url>"、"剪藏这个链接"、"帮我评分这篇文章"。
---

# Web Clipper Skill

## 触发条件

- 用户发送 `clip <url>`
- 用户发送 `剪藏 <url>`
- 用户发送 `帮我评分 <url>`
- 用户粘贴一个 URL 并希望"存入知识库"

## 使用方法

```bash
# 标准用法（评分 + 入库 + Telegram 通知）
PYTHONPATH=/Users/hugh/Desktop/Antigravity \
  python skills/web_clipper/clipper.py "https://example.com/article"

# 静默模式（不推 Telegram，适合批量）
python skills/web_clipper/clipper.py "https://..." --silent

# 降低入库门槛（允许 7 分以上入库）
python skills/web_clipper/clipper.py "https://..." --min-score 7.0
```

## Python API

```python
from skills.web_clipper.clipper import clip_url

result = clip_url("https://example.com/article")
# 返回：
# {
#   "url":      "https://...",
#   "title":    "文章标题",
#   "score":    8.7,
#   "reason":   "一句话理由",
#   "axiom":    "提炼的底层公理",
#   "written":  True,          # 是否写入 Inbox
#   "filepath": "/path/to/Clip - xxx.md",
# }
```

## 流程说明

```
URL
 ↓ trafilatura.fetch_url() + extract()   → 高质量正文（≤6000字）
 ↓ 回退: BeautifulSoup <p> 抽取
 ↓
 ↓ Gemini 2.0 Flash via OpenRouter
 ↓ system_prompt: Bouncer 认知守门员标准
 ↓ → score / reason / axiom_extracted
 ↓
 ├─ score ≥ 8.0 → 写入 00_Inbox/Clip - {title}.md
 │                  frontmatter: { status: pending, score, source }
 │                  → inbox_processor 下次运行时自动处理
 │
 └─ score < 8.0 → 仅 Telegram 通知，不入库
```

## 与其他组件的关系

- **被 obsidian_bridge 支撑**：使用 `get_vault()` 定位 Inbox 路径
- **数据交接给 inbox_processor**：写入的笔记带 `status: pending`，10:30 Cron 自动消费
- **复用 bouncer 的 telegram_notify**：同一个 Telegram Bot 推送
- **评分标准完全一致**：同一份 SYSTEM_PROMPT，确保高低分判断与 bouncer 一致

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GEMINI_API_KEY` | *(必填)* | OpenRouter API Key |
| `CLIPPER_MIN_SCORE` | `8.0` | 入库分数门槛 |
| `OBSIDIAN_VAULT` | `/Users/hugh/Documents/Obsidian/AINotes` | Vault 路径 |
| `TELEGRAM_CHAT_ID` | *(from .env)* | 通知目标 |
