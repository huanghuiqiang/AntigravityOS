# 🚀 Antigravity OS

> **个人 AI 操作系统**：自动过滤信息噪音、提炼认知公理、驱动知识沉淀的 Agent 平台。

---

## 🛠 工程化重构 (V2)

系统已完成工程化重构，核心变化：
1. **统一配置中心** (`agos/config.py`)：消灭硬编码路径，支持 `.env` 灵活配置。
2. **共享基础设施** (`agos/frontmatter.py`, `agos/notify.py`)：统一 YAML 解析逻辑与 Telegram 推送入口。
3. **标准包结构**：采用 `pyproject.toml` 管理依赖，支持 `pip install -e .` 安装。
4. **自动化测试**：引入 `pytest` 覆盖核心逻辑，确保系统稳健。

---

## 系统架构

```
Antigravity OS
│
├── agos/                   → 核心共享包 (Config, Notify, Frontmatter)
│
├── agents/                 → 有状态的任务 Agent
│   ├── cognitive_bouncer/  → RSS 扫描 → LLM 评分 → Obsidian Inbox
│   ├── inbox_processor/    → 消费 pending 条目 → NotebookLM 合成 → 归档
│   ├── axiom_synthesizer/  → 聚合碎片 → 提炼正式 Axiom → 更新地图
│   ├── daily_briefing/     → 每日早报统计
│   └── knowledge_auditor/  → 知识库健康审计
│
├── skills/                 → 原子化能力库
│   ├── obsidian_bridge/    → Obsidian Vault CRUD API
│   ├── web_clipper/        → 即时剪报评分
│   ├── vault_query/        → 自然语言查询 Vault
│   └── global_tools/       → PDF 解析、YouTube 提取等
│
└── data/                   → 数据资产
    ├── obsidian_inbox      → 软链接至 Obsidian 00_Inbox
    └── logs/               → 统一日志归集
```

---

## 快速开始

### 1. 环境安装

```bash
# 推荐使用虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装项目（含开发依赖）
pip install -e ".[dev]"
```

### 2. 配置

在项目根目录创建 `.env` 文件：

```ini
# 路径配置
OBSIDIAN_VAULT="/Users/hugh/Documents/Obsidian/AINotes"

# API Keys
OPENROUTER_API_KEY="sk-..."
GEMINI_API_KEY="sk-..." # 兼容旧配置

# Telegram
TELEGRAM_BOT_TOKEN="..."
TELEGRAM_CHAT_ID="..."
```

### 3. 运行测试

```bash
pytest
```

---

## 核心管道 (Pipeline)

1. **Bouncer (08:00)**: 巡逻 RSS 订阅源，发现 >8.0 分内容投递至 Inbox。
2. **Auditor (周一/每4h)**: 检查知识孤岛、积压条目，维持系统熵减。
3. **Briefing (07:50)**: 推送今日早报，引导重点阅读与提炼。
4. **Processor (10:30)**: 自动调用 NotebookLM 为高分文章生成深度报告。

---

## 维护者指令

- **添加新 Agent**: 放在 `agents/` 下，引用 `from agos import ...` 获取配置和推送。
- **添加新原子能力**: 放在 `skills/` 下，确保函数无状态可测试。
- **修改系统逻辑**: 先在 `tests/` 下编写测试用例。

---

*Antigravity OS — 让信息为你工作，而不是淹没你。*
