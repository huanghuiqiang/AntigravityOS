# 🤖 Antigravity OS | Agent Operations Protocol

This document serves as the high-level map for AI Agents to understand and navigate the Antigravity infrastructure.

## 🗺️ System Map (Breadcrumbs for LLMs)
- **ROOT**: `/Users/hugh/Desktop/Antigravity`
- **CORE**: `./core/openClaw` - The main orchestrator.
- **SKILLS**: `./skills/` - Stateless atomic capabilities.
  - `global_tools/`: Generic utilities (YouTube, PDF, etc.)
  - `notebooklm/`: Deep synthesis and artifact generation.
  - `obsidian_bridge/`: Obsidian Vault CRUD API (read/write/frontmatter/scan).
- **AGENTS**: `./agents/` - Stateful task-specific services.
  - `cognitive_bouncer/`: Information sifting & Axiom extraction → writes `status: pending` to Inbox.
  - `inbox_processor/`: Consumes pending Inbox items → NotebookLM synthesis → archives → Telegram.
- **DATA BUS**: `./data/obsidian_inbox` -> Linked to Obsidian `/Users/hugh/Documents/Obsidian/AINotes/00_Inbox`

## 🔄 Full Pipeline (End-to-End)

```
[08:00 Cron] cognitive_bouncer.py
  → RSS feeds → LLM scoring → score ≥ 8.0
  → 00_Inbox/Bouncer - {title}.md
     frontmatter: { status: pending, score, source, title }

[10:30 Cron] inbox_processor.py
  → scan_pending(min_score=8.0)
  → notebooklm: create notebook → add source → generate study-guide
  → append report to note
  → update frontmatter: { status: done, processed_at, notebook_id }
  → archive to 00_Inbox/YYYY-MM-DD/
  → Telegram push: summary report
```

## 🛠️ Inter-Agent Communication (接力协议)
Agents communicate via **Obsidian Metadata (YAML)** within the Data Bus.

### Bouncer Entry Schema (写入端)
```yaml
---
status: pending      # choices: [pending, synthesizing, done, error]
score: 9.5
source: "URL_HERE"
title: "Article Title"
created: "2026-02-21"
tags: [BouncerDump]
---
```

### InboxProcessor Update Schema (消费端)
```yaml
---
status: done
processed_at: "2026-02-21 10:35"
notebook_id: "abc123de-..."
---
```

## 🐍 Execution Environment
- **Initialization**: Set `PYTHONPATH=/Users/hugh/Desktop/Antigravity` before execution.
- **obsidian_bridge**: `from skills.obsidian_bridge.bridge import scan_pending, write_note, ...`
- **youtube_downloader**: `from skills.global_tools.youtube_downloader import extractor`

## 🧭 Direction for Sub-Agents
1. **Always Check the Inbox**: `scan_pending()` from `obsidian_bridge` to find tasks.
2. **Prioritize Axioms**: Don't just summarize; find the "Antigravity Axiom" (recursive, top-down friction point).
3. **Respect the Gatekeeper**: Bouncer defines what is worth processing. Do not process `score < 8.0` unless explicitly asked.
4. **Use obsidian_bridge**: Never write raw files directly. Always use `write_note()` / `update_frontmatter()`.

## ⏰ Cron Schedule
| Time  | Agent | Action |
|-------|-------|--------|
| 08:00 | cognitive_bouncer | RSS scan → score → write Inbox |
| 10:30 | inbox_processor   | NotebookLM synthesis → archive → notify |

Install: `chmod +x scripts/setup_cron.sh && ./scripts/setup_cron.sh`

---
*Updated: 2026-02-21*
