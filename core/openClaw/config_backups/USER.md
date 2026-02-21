# USER.md - About Your Human

_Learn about the person you're helping. Update this as you go._

- **Name:**
- **What to call them:**
- **Pronouns:** _(optional)_
- **Timezone:**
- **Notes:** 极其关注 Token 消耗和运行成本。在大规模 Token 消耗或使用高价模型操作前，必须主动提醒。

## Context

- **关注点:** AI 自动化、知识管理、成本优化。
- **项目:** openClaw 自动化、AI 新闻简报。AntigravityOS（自动化知识管道）。
- **发布规范 (X/Twitter):** 特别注意普通账号 280 字符限制。内容建议控制在 240 字符以内以确保安全。

## Obsidian 知识库（必须用脚本查询）

Hugh 有一个 **Obsidian AINotes Vault**，包含 Axiom 公理、笔记、项目文档、Inbox。

**⚠️ 关键规则：当 Hugh 询问任何关于「笔记」「知识库」「有没有关于X的记录」「Inbox」「Axiom」「pending」的问题时，必须运行以下脚本获取真实数据，严禁凭记忆臆造。**

```bash
# 搜索笔记（最常用）
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py search "关键词"

# 读取特定笔记
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py get "笔记名"

# 查看待处理文章
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py pending

# 列出所有公理
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py axioms

# Inbox 统计
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py stats

# 最近入库
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py recent 10
```

详见 skill: `vault_query`


---

The more you know, the better you can help. But remember — you're learning about a person, not building a dossier. Respect the difference.
