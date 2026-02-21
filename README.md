# 🚀 Antigravity OS

> **个人 AI 操作系统**：自动过滤信息噪音、提炼认知公理、驱动知识沉淀的 Agent 平台。

---

## 系统架构

```
Antigravity OS
│
├── core/openClaw/          → Pi 🧊 全局 AI 指挥中枢（Telegram + Cron + LLM Router）
│
├── skills/                 → 原子化、无状态的能力库
│   ├── obsidian_bridge/    → Obsidian Vault CRUD API
│   ├── notebooklm/         → Google NotebookLM 完整 API
│   ├── web_clipper/        → URL → 即时评分 → Obsidian 入库
│   └── global_tools/       → YouTube 字幕提取、PDF 解析等
│
├── agents/                 → 有状态的、定时驱动的任务 Agent
│   ├── cognitive_bouncer/  → RSS 扫描 → LLM 评分 → Obsidian Inbox [submodule]
│   └── inbox_processor/    → 消费 pending 条目 → NotebookLM 合成 → 归档
│
└── data/obsidian_inbox     → 数据总线（symlink → Obsidian 00_Inbox）
```

---

## 完整数据流（Pipeline）

```
[手动触发]  clip <URL>  →  web_clipper
                              ↓ 即时评分（Gemini Flash）
                              ↓
[08:00 Cron] cognitive_bouncer  →  RSS 扫描 → 评分
                              ↓
              Obsidian 00_Inbox
              { status: pending, score ≥ 8.0, source, title }
                              ↓
[10:30 Cron] inbox_processor  →  notebooklm: study-guide 报告
                              ↓  update status: done
                              ↓  归档到 00_Inbox/YYYY-MM-DD/
                              ↓
                        Telegram 推送摘要
```

---

## 快速开始

### 环境初始化

```bash
# 克隆（含 submodule）
git clone --recurse-submodules git@github.com:huanghuiqiang/AntigravityOS.git
cd AntigravityOS

# 安装依赖
pip install pyyaml python-dotenv requests httpx beautifulsoup4 trafilatura

# 配置 API Key（复制 bouncer 的 .env）
cp agents/cognitive_bouncer/.env.example agents/cognitive_bouncer/.env
# 填入 GEMINI_API_KEY 和 TELEGRAM_CHAT_ID
```

### 安装定时任务

```bash
chmod +x scripts/setup_cron.sh
./scripts/setup_cron.sh
# 08:00 → bouncer, 10:30 → inbox_processor
```

### 手动触发 Web Clipper

```bash
# 即时剪报一篇文章
PYTHONPATH=. python skills/web_clipper/clipper.py "https://example.com/article"

# 也可通过 Telegram 对 Pi 说：
# clip https://example.com/article
```

---

## Skills 目录

| Skill | 描述 | 状态 |
|-------|------|------|
| `obsidian_bridge` | Obsidian Vault 读写 CRUD API | ✅ 完成 |
| `notebooklm` | NotebookLM 完整 API（notebook/source/generate/download） | ✅ 完成 |
| `web_clipper` | URL 即时评分入库，无需等 cron | ✅ 完成 |
| `global_tools/youtube_downloader` | YouTube URL → 字幕文本 | ✅ 完成 |
| `pdf_ingester` | PDF → 文本提取 → Bouncer 评分管道 | 📋 计划中 |

## Agents 目录

| Agent | 描述 | 状态 |
|-------|------|------|
| `cognitive_bouncer` | RSS→LLM 评分→Obsidian，08:00 Cron | ✅ 完成 |
| `inbox_processor` | pending→NotebookLM→归档, 10:30 Cron | ✅ 完成 |
| `axiom_synthesizer` | 聚合 done 笔记→提炼新 Axiom→写入认知地图 | 📋 计划中 |
| `knowledge_auditor` | 扫描孤立笔记、过期 Axiom、生成 Vault 健康报告 | 📋 计划中 |
| `daily_briefing` | 每日汇总 pending 条目 → Telegram 早报 | 📋 计划中 |

---

## Roadmap

### ✅ Phase 1 — 核心管道（已完成）
- [x] Cognitive Bouncer：RSS 过滤 + LLM 评分 + Obsidian 投递
- [x] Obsidian Bridge：Vault CRUD 工具库
- [x] Inbox Processor：NotebookLM 合成 + 自动归档
- [x] Telegram 推送集成
- [x] Cron 流水线（08:00 → 10:30）

### ✅ Phase 2 — 即时触发（当前）
- [x] Web Clipper：URL → 即时评分 → Inbox（无需等 cron）

### 📋 Phase 3 — 知识提炼闭环
- [ ] **Axiom Synthesizer**：聚合本周所有 done 笔记，AI 提炼新 Axiom，自动更新 `000 认知架构地图.md`
- [ ] **PDF Ingester**：PDF → 文本 → 进入 Bouncer 评分管道（补全 global_tools）
- [ ] **Daily Briefing Agent**：每日 07:50 推送 Inbox 待处理摘要 + 天气

### 📋 Phase 4 — 系统健壮性
- [ ] **Knowledge Auditor**：定期扫描孤立笔记、检测无链接 Axiom、生成 Vault 健康报告
- [ ] **Pi 感知 obsidian_bridge**：让 OpenClaw Pi 通过 Telegram 实时问答 Vault 内容
- [ ] **VPS 部署**：Gateway 迁移到 24/7 在线服务器，Cron 不依赖本机开机

---

## 核心依赖

| 工具 | 用途 |
|------|------|
| OpenRouter → Gemini 2.0 Flash | LLM 评分（低成本） |
| OpenRouter → Claude Opus 4 | Pi 主力对话模型 |
| NotebookLM CLI (`notebooklm-py`) | 深度报告/Podcast 生成 |
| Obsidian + AINotes Vault | 知识持久化 + 数据总线 |
| Telegram Bot | 推送通知 + 指令入口 |
| OpenClaw Gateway | Pi Agent 运行时 |

---

## 设计原则

1. **Obsidian 是数据总线**：Agent 间通过 YAML frontmatter 传递状态（`status: pending/done/error`）
2. **Skills 无状态**：每个 skill 是纯函数，可独立测试，不保存运行时状态
3. **低 Token 优先**：过滤/评分用 Gemini Flash，合成/对话用 Claude
4. **自我描述**：每个 skill/agent 有 `SKILL.md` / `README.md`，LLM 可自主读取并调用

---

*Antigravity OS — 让信息为你工作，而不是淹没你。*
