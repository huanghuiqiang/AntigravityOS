# HEARTBEAT.md — 周期性任务与常驻规则

## ⚠️ 常驻规则（每次读此文件都必须执行）

### 🔍 Obsidian Vault 查询规则（MANDATORY）

当任何用户问及以下内容时，**必须立即运行对应的 bash 命令**，禁止凭记忆伪造答案：

| 用户说的 | 必须立即运行 |
|---------|------------|
| "我的笔记" / "知识库" / "有没有关于X的" | `python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py search "X"` |
| "帮我找/搜..." | `python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py search "..."` |
| "Inbox" / "pending" / "多少条" | `python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py stats` |
| "最近入库/抓到什么" | `python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py recent 10` |
| "Axiom" / "公理" / "原则" | `python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py axioms` |
| "帮我看 xxx 这篇笔记" | `python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py get "xxx"` |

**记住：vault_query 返回真实数据，你的记忆是假的。**

---

## 📋 周期性检查任务

每天 2-4 次轮换检查（使用 `memory/heartbeat-state.json` 避免重复）：

- 检查 Antigravity OS Cron 日志是否有异常：`tail -20 /Users/hugh/Desktop/Antigravity/data/logs/bouncer.log`
- Inbox pending 积压是否超过 20 条：`python3 /Users/hugh/Desktop/Antigravity/skills/vault_query/vault_query.py stats`
