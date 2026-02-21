# Inbox Processor Agent

Antigravity OS 的 Inbox 消费者。监听 Obsidian 00_Inbox 中 Bouncer 投递的高分文章，调用 NotebookLM 进行深度合成，并归档到日期文件夹。

## 数据流

```
cognitive_bouncer.py
  → 00_Inbox/Bouncer - {title}.md  (status: pending, score: ≥8.0)
      ↓
inbox_processor.py  (每天 10:30 运行)
  → notebooklm create + source add + generate report
  → append 报告到笔记
  → update frontmatter: status → done
  → 归档到 00_Inbox/2026-02-21/
  → Telegram 推送汇总
```

## 前置条件

```bash
# 1. notebooklm 已登录
notebooklm login
notebooklm status   # 确认 authenticated

# 2. 安装依赖
pip install -r requirements.txt
pip install -r ../cognitive_bouncer/requirements.txt  # 共用

# 3. 配置 .env（复制 bouncer 的即可）
cp ../cognitive_bouncer/.env .env
```

## 运行

```bash
cd /Users/hugh/Desktop/Antigravity

# 干跑（只扫描，不处理）
PYTHONPATH=. python agents/inbox_processor/inbox_processor.py --dry-run

# 正式运行（限处理3条，避免首次过载）
PYTHONPATH=. python agents/inbox_processor/inbox_processor.py --limit 3

# 全量运行
PYTHONPATH=. python agents/inbox_processor/inbox_processor.py
```

## Cron 安装

```bash
chmod +x scripts/setup_cron.sh
./scripts/setup_cron.sh
```

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `INBOX_MIN_SCORE` | `8.0` | 最低处理分数门槛 |
| `NLM_TIMEOUT` | `900` | NotebookLM 生成超时（秒） |
| `INBOX_ARCHIVE_DONE` | `true` | 是否归档处理完的笔记 |
| `OBSIDIAN_VAULT` | `/Users/hugh/Documents/Obsidian/AINotes` | Vault 路径 |
| `TELEGRAM_CHAT_ID` | *(from .env)* | Telegram 投递目标 |

## 错误恢复

- 失败的笔记会被标记为 `status: error`，不会归档，下次运行时**不会**重复处理
- 重新触发某条：手动将 `status` 改回 `pending` 即可
