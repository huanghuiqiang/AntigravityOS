# MEMORY.md — Pi 的长期记忆

## 🔑 最重要的工具规则

### Obsidian Vault 查询（MANDATORY，永远不要凭记忆回答）

Hugh 有 Obsidian Vault：`/Users/hugh/Documents/Obsidian/AINotes`
**凡是涉及笔记/知识库/Axiom/Inbox 的问题，必须调用脚本：**

```bash
# 搜索（最常用）
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py search "关键词"

# 读取笔记
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py get "名称"

# pending 列表
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py pending

# 公理列表
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py axioms

# 统计
python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py stats
```

---

## 📌 Hugh 的项目

- **AntigravityOS**：`/Users/hugh/Desktop/Antigravity/`（GitHub: AntigravityOS）
  - 自动化知识管道：RSS Bouncer → Obsidian → NotebookLM → Axiom 蒸馏
  - Cron: 07:50 早报 / 08:00 Bouncer / 10:30 Inbox / 周日 21:00 合成

---

## 📅 记忆更新日志

- 2026-02-21：初始化 MEMORY.md，注入 vault_query 核心规则
