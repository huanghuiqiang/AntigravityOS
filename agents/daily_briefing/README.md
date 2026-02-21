# Daily Briefing Agent

每天 07:50 通过 Telegram 推送系统早报。

## 内容结构

```
🌅 Antigravity OS — 今日早报
2026-02-21 (金曜日)

🟢 系统健康度 95/100
📥 总入库 67 | ⏳ Pending 3 | ✅ Done 60 | ❌ Error 0

🔥 今日高价值入库 Top 5
  💎 [9.5] LLM Post-Skill Generation ... RSS·simonwillison.net
  🥇 [8.8] How to debug faster       ... Clip·matklad.github.io

⏰ Cron 状态
  🤖 Bouncer:        ✅ 08:00 (0h 前)
  🧠 InboxProcessor: ✅ 10:30 (2h 前)

📊 本周趋势（7天）
  入库: ▁▂▃▅▇▆▄  42 条
  完成: ▁▁▂▄▆▅▃  35 条

🎯 今日重点（最高分 pending）
  💎 [9.5] The Minimal Agent Architecture
```

## 安装 Cron

```bash
# 在 setup_cron.sh 中追加（或手动 crontab -e）：
50 7 * * *  cd /Users/hugh/Desktop/Antigravity && PYTHONPATH=. python agents/daily_briefing/daily_briefing.py >> data/logs/daily_briefing.log 2>&1
```

## 手动运行

```bash
# 正式运行
PYTHONPATH=/Users/hugh/Desktop/Antigravity \
  python agents/daily_briefing/daily_briefing.py

# Mock 模式（注入示例数据，测试推送格式）
PYTHONPATH=/Users/hugh/Desktop/Antigravity \
  python agents/daily_briefing/daily_briefing.py --mock
```
