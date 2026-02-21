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

## 🚀 Antigravity OS | AI 时代工程原则 (2026)

**核心结论：工程原则约束下的极致 MVP 速度。**
速度依然是王道，但“脏速”在 AI 时代会被成倍放大。AI 放大了已有的工程纪律，而非取代它。

### 1. MVP 演进与工程投入权衡

| 阶段 / 场景 | 优先级排序 | 最小工程护栏投入 (推荐) |
| --- | --- | --- |
| **Idea → 最初原型** | MVP 速度 >> 工程 | 1. 核心层引入配置管理 (`pydantic-settings`)<br>2. 划定基本 Agent/模块边界<br>3. 实现最基础的日志记录 |
| **原型 → 自用/小范围** | MVP 可用性 ≈ 工程 | 1. 引入 SQLite 替代脆弱基于文件的存储<br>2. 覆盖核心链路单元测试 (Mock LLM)<br>3. 死信队列 + 关键节点告警 |
| **自用 → 分享/协作** | 工程 >> MVP 花哨度 | 1. 至少 60% 核心测试覆盖率<br>2. 标准化 CI/CD 构建 (GitHub Actions)<br>3. 强化 Lint & 类型提示 (Type hints) |
| **生产 / 长期维护** | 工程 >> 一切 | 1. 深度可观测性 (指标、Tracing)<br>2. 结构化版本迁移与 Schema 化存储<br>3. 完备的架构决策记录 (ADR) |

### 2. Antigravity Agent 开发底线 (Day 1 要求)
在用工具疯狂提速的同理，所有新增功能必须坚守以下 3 条强约束：
1. **统一配置**：所有路径、参数、API 密钥必须全部收敛至 Config。
2. **强类型 IO**：所有 Agent Nodes 的 Input/Output 必须声明强制的 Pydantic 模型 (Schema)。
3. **带防故障的写入**：所有核心系统或文件变更必须包裹 `try-except`，并在异常时捕获日志（哪怕是最简单的 stdout/stderr）。

### 3. AI 时代的新型工程价值序
相比传统理念，在本项目中应遵循以下新式优先级判定：
1. **Prompt/上下文工程 > 传统 Clean Code**（大模型是系统的最核心依赖）。
2. **可测试性 > 完美抽象**（能对 LLM 输出节点做有效 Mock 远比遵循 100% SOLID 重要）。
3. **可观测性 > 注释**（能够精确追踪每个 Agent 消耗的 Token 量与执行阻塞点才是关键）。
4. **架构决策可逆 > 一次到位**（通过抽象避免技术栈锁定，确保能够从 File → SQLite → Postgres 无缝切换）。

---
*Updated: 2026-02-21*
