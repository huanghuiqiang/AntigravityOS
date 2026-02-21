---
tags:
  - Project
  - SystemCore
  - AntigravityOS
status: active
created: "2026-02-21"
github: "https://github.com/huanghuiqiang/AntigravityOS"
---

# Project — Antigravity OS 开发全记录

> **Core Mission**：抵抗认知熵增，将被动接收的信息流自动转化为结构化知识资产。
> **核心理念**：让信息为你工作，而不是淹没你。

---

## 🗺️ 系统架构全景

```
Antigravity OS (github: AntigravityOS)
│
├── core/openClaw/              Pi 🧊 全局 AI 指挥中枢
│   └── skills/                Pi 调用的原生 Skill 库
│
├── agents/                    有状态的、定时驱动的任务 Agent
│   ├── cognitive_bouncer/     RSS 扫描 → 评分 → Inbox [Git Submodule]
│   ├── inbox_processor/       消费 pending → NotebookLM 合成 → 归档
│   ├── axiom_synthesizer/     碎片公理 → LLM 蒸馏 → 认知地图（每周日）
│   ├── knowledge_auditor/     全库审计（孤岛/积压/元数据）+ 即时警报 ✅
│   └── daily_briefing/        每日 07:50 Telegram 早报（集成审计报告）
│
├── skills/                    原子化、无状态的能力库
│   ├── vault_query/           Pi 调用的语义搜索/统计/笔记读取 CLI ✅
│   ├── obsidian_bridge/       Obsidian Vault CRUD API
│   ├── notebooklm/            NotebookLM 完整 API
│   └── global_tools/          PDF 入库 / YouTube 下拉等原子工具
│
├── scripts/
│   ├── stats.py               集成 Auditor 指标的共享数据收集层
│   ├── dashboard.py           终端 TUI（包含审计视图）
│   ├── generate_report.py     HTML Dashboard（包含可视化审计卡片）
│   └── setup_cron.sh          定时任务全自动化安装
│
└── data/
    ├── obsidian_inbox → symlink → Obsidian 00_Inbox
    └── logs/                  系统运行日志
```

---

## 🔄 完整数据流（Pipeline）

```
[07:50 Cron]  daily_briefing       推送 Telegram 早报（含健康警报 + 审计摘要）
                                         │
[08:00 Cron]  cognitive_bouncer    RSS 扫描 → LLM 评分 → 写 Inbox
                                         │
[每4h Cron]   knowledge_auditor    静默巡检健康分 → 若 <60 分立即触发【紧急警报】
                                         │
[随时 Pi 对话] vault_query           Hugh 访问 Telegram Pi → 语义搜索/查 Pending /查 Axiom
                                         │
[10:30 Cron]  inbox_processor      NotebookLM 合成报告 → 归档 → 发送处理摘要
                                         │
[周日 21:00]  axiom_synthesizer    扫描碎片 → 提炼公理 → 更新认知架构地图
                                         │
[随时触发]     HEARTBEAT 巡检       Pi 心跳发现健康异常 → 在会话中【主动提醒】Hugh
```

---

## ✅ 已完成功能（Phase 1-4.1）

### Phase 1-3 — 管道与基础输入 (已固化)
*已实现：RSS Bouncer, NotebookLM Processor, PDF Ingester, Web Clipper, Axiom Synthesizer.*

### Phase 4.1 — 治理、交互与主动性 (New)

| 组件 | 功能 | 状态 |
|------|------------|------|
| `knowledge_auditor` | **全库治理**：孤岛 Axiom 检测（Linkage 驱动）、Inbox 10天积压预警、元数据审计。 | ✅ |
| `vault_query` | **Pi 语义中枢**：通过 Telegram 指挥 Pi 搜索全库、读取笔记、拉取 Pending 列表、查看统计。 | ✅ |
| **Active Alerts** | **主动防御**：定期静默巡检，健康度异常立即推送警报；HEARTBEAT 注入，使 Pi 具备主动劝诱编织的能力。 | ✅ |
| **Dashboard V2** | **全链路可视化**：TUI 与 HTML 版均集成「知识库健康」卡片，孤立公理一目了然。 | ✅ |

---

## 📋 Roadmap（Phase 4.2 待开发）

### 高优先级

  - 推荐：Hetzner CAX11（ARM，€3.79/月）+ systemd 代替 cron

- [ ] **Axiom Synthesizer 增强**
  - 当前只采集最近 30 条碎片（`MAX_BATCH=30`），未来按"未合成"状态增量处理
  - 追加 `synthesized: true` frontmatter 标记，实现真正增量去重

- [ ] **Web Clipper → Pi Telegram 联动**
  - 配置 Pi 的 pattern 识别：用户发 `clip https://...`
  - Pi 自动调用 `web_clipper/clipper.py`，无需 CLI

### 低优先级

- [ ] **Daily Briefing 增强**：加入天气/日历提醒集成
- [ ] **Vault Inner-Linker**：自动为相关笔记建立 `[[wikilink]]`

---

## 🛠️ 快速操作手册

```bash
# 即时剪报
PYTHONPATH=. python skills/web_clipper/clipper.py "https://..."

# PDF 入库
PYTHONPATH=. python skills/global_tools/pdf_ingester/pdf_ingester.py ~/paper.pdf

# 终端健康看板
PYTHONPATH=. python scripts/dashboard.py --watch

# HTML 可视化报告（自动打开浏览器）
PYTHONPATH=. python scripts/generate_report.py

# 手动触发公理蒸馏
PYTHONPATH=. python agents/axiom_synthesizer/synthesizer.py --dry-run

# 安装/更新 Cron
./scripts/setup_cron.sh

# 查看日志
tail -f data/logs/bouncer.log
tail -f data/logs/daily_briefing.log
```

---

## 🔗 关键链接

- **GitHub**: [AntigravityOS](https://github.com/huanghuiqiang/AntigravityOS)
- **Submodule**: [Cognitive-Bouncer](https://github.com/huanghuiqiang/Cognitive-Bouncer)
- **认知地图**: [[000 认知架构地图]]
- **Obsidian Inbox**: [[00_Inbox]]

---

## 📐 设计原则（Production Rules）

1. **Obsidian 是数据总线**：Agent 间通过 YAML frontmatter 传递状态（`status: pending → done → error`）
2. **Skills 无状态**：每个 skill 是纯函数，独立可测，不保存运行时状态
3. **低 Token 优先**：过滤/评分用 Gemini Flash（便宜快），合成/对话用 Claude（质量高）
4. **只追加，不修改**：Synthesizer 等写入操作均为幂等追加，不破坏已有结构
5. **自我描述**：每个 skill/agent 有 `SKILL.md` / `README.md`，LLM 可自主读取并调用
6. **可观测性**：所有 Agent 写日志，Dashboard 统一展示，瓶颈一眼可见

---

*最后更新：2026-02-21 | Antigravity OS v2026.2*
