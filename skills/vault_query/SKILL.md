---
name: vault_query
description: 查询和搜索 Hugh 的 Obsidian Vault（AINotes 知识库）。支持全文搜索笔记、读取特定 Axiom 或 Project 文档、查看 Inbox 状态、列出待处理高分文章。激活条件：用户询问"我的笔记里有没有关于..."、"帮我找 Axiom-xxx"、"Inbox 现在有多少 pending"、"最近入库了什么"等。
---

# Vault Query Skill

Hugh 的 Obsidian AINotes Vault 的查询接口。通过此 Skill，你可以实时访问 Hugh 的第二大脑。

## Vault 结构

```
/Users/hugh/Documents/Obsidian/AINotes/
├── 000 认知架构地图.md        核心认知地图（所有 Axiom 的 MOC）
├── Axiom - *.md              公理笔记（第一性原理）
├── 00_Inbox/                 信息入库区（Bouncer/Clip/PDF 产出）
│   ├── *.md                  带 status: pending/done 的笔记
│   └── YYYY-MM-DD/           归档子文件夹
├── Projects/                 项目文档
└── Protocol-*/Framework-*    方法论笔记
```

## 使用方法

所有命令通过 `python3` 调用：

```bash
SCRIPT="/Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py"

# 全文搜索（文件名 + 正文，按命中数排序）
python3 $SCRIPT search "Agent 架构"
python3 $SCRIPT search "LLM 推理 System2"

# 读取特定笔记（模糊文件名匹配）
python3 $SCRIPT get "认知架构地图"
python3 $SCRIPT get "Axiom - 工具是 Agent 的感官"
python3 $SCRIPT get "Daily Briefing"

# 查看 Inbox 待处理队列（按分数排序）
python3 $SCRIPT pending
python3 $SCRIPT pending --limit 5

# 列出所有 Axiom 公理（含摘要）
python3 $SCRIPT axioms

# Inbox 状态快照
python3 $SCRIPT stats

# 最近入库的笔记
python3 $SCRIPT recent
python3 $SCRIPT recent 10
```

## 典型对话场景

| 用户说 | Pi 应该调用 |
|--------|------------|
| "我笔记里有没有关于 Agent 的内容？" | `search "Agent"` |
| "帮我找工具与本能那条公理" | `get "工具是 Agent 的感官"` |
| "Inbox 现在有多少待处理的？" | `pending` 或 `stats` |
| "最近 Bouncer 抓到了什么好文章？" | `recent 10` |
| "帮我看一下认知架构地图" | `get "000 认知架构地图"` |
| "列出我所有的公理" | `axioms` |

## 环境变量

| 变量 | 默认值 |
|------|--------|
| `OBSIDIAN_VAULT` | `/Users/hugh/Documents/Obsidian/AINotes` |

## 输出格式说明

- 搜索结果包含：标题、文件路径、关键词上下文摘要
- 笔记全文会截断至 4000 字符（防止 token 爆炸）
- 所有输出为 Markdown 格式，适合直接回复 Telegram
