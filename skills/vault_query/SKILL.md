---
name: vault_query
description: "**[MANDATORY TOOL]** Hugh 的 Obsidian 个人知识库查询工具。当用户问及「我的笔记」「知识库」「有没有关于X的笔记/公理/记录」「Inbox里有什么」「pending了多少」时，必须调用此脚本获取真实数据——严禁凭记忆臆造答案。脚本路径: python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py"
---

# Vault Query Skill（MANDATORY — 禁止跳过）

> **⚠️ 重要规则**：凡是涉及 Hugh 的笔记、Obsidian、知识库、Axiom、Inbox 的问题，**必须先运行下方命令获取真实数据**，严禁凭 LLM 记忆或上下文猜测回答。

## 脚本路径

```
/Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py
```

## 调用方式（直接在 bash 中运行）

```bash
# 1. 全文搜索笔记（最常用）
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py search "架构"
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py search "Agent 系统设计"

# 2. 读取某篇笔记全文（模糊文件名匹配）
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py get "认知架构地图"
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py get "工具是 Agent 的感官"

# 3. 查看 Inbox 待处理队列
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py pending

# 4. 列出所有 Axiom 公理
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py axioms

# 5. Inbox 状态统计
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py stats

# 6. 最近入库的笔记
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py recent 10
```

## 触发场景（这些情况必须调用）

| 用户说 | 必须调用 |
|--------|---------|
| "我的笔记里有没有关于X的？" | `search "X"` |
| "帮我搜索/找一下..." | `search "..."` |
| "有没有关于X的公理/Axiom？" | `search "X"` 或 `axioms` |
| "Inbox 里有什么？" / "pending 了多少？" | `pending` 或 `stats` |
| "最近抓到了什么文章？" | `recent 10` |
| "帮我看 XXX 这篇笔记" | `get "XXX"` |
| "所有 Axiom 是什么？" | `axioms` |

## Vault 结构（供参考）

```
/Users/hugh/Documents/Obsidian/AINotes/
├── 000 认知架构地图.md     → 核心 MOC，包含所有 Axiom 引用
├── Axiom - *.md           → 公理笔记（第一性原理）
├── 00_Inbox/              → Bouncer/WebClip/PDF 产出
│   └── YYYY-MM-DD/Archive/ → 归档子文件夹
└── Projects/              → 项目文档
```

## 重要说明

- 搜索结果按命中次数排序，文件名匹配权重 ×3
- 笔记全文最多返回 4000 字符
- Vault 路径固定为 `/Users/hugh/Documents/Obsidian/AINotes`
- **不要用 find/ls 自行搜索 Vault，用此脚本效率更高且输出格式更好**
