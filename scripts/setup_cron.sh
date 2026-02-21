#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# Antigravity OS | Cron 流水线（完整版）
#
# 安装方法：
#   chmod +x scripts/setup_cron.sh && ./scripts/setup_cron.sh
#
# 调度总览：
#   07:50  Daily Briefing      早报推送（Telegram）
#   08:00  Cognitive Bouncer   RSS 扫描 + 评分 + 写 Inbox
#   10:30  Inbox Processor     NotebookLM 合成 + 归档 + 通知
#   21:00  Axiom Synthesizer   每周日：蒸馏公理 + 更新认知地图
# ─────────────────────────────────────────────────────────────────

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/data/logs"
mkdir -p "$LOG_DIR"

# Python 解释器（优先使用虚拟环境）
PYTHON="${ROOT}/.venv/bin/python3"
if [ ! -f "$PYTHON" ]; then
    PYTHON="$(which python3)"
fi

echo "🐍 Python: $PYTHON"
echo "📁 Root:   $ROOT"
echo ""

# ── 构建 cron 内容 ────────────────────────────────────────────────

# 07:50 - 每日早报（Bouncer 运行前推送昨日摘要）
CRON_BRIEFING="50 7 * * *  cd $ROOT && PYTHONPATH=$ROOT $PYTHON agents/daily_briefing/daily_briefing.py >> $LOG_DIR/daily_briefing.log 2>&1"

# 08:00 - Cognitive Bouncer：RSS 扫描 + 评分 + 写 Inbox
CRON_BOUNCER="0 8 * * *   cd $ROOT && PYTHONPATH=$ROOT $PYTHON agents/cognitive_bouncer/bouncer.py >> $LOG_DIR/bouncer.log 2>&1"

# 10:30 - Inbox Processor：NotebookLM 合成 + 归档 + 通知
CRON_INBOX="30 10 * * *  cd $ROOT && PYTHONPATH=$ROOT $PYTHON agents/inbox_processor/inbox_processor.py >> $LOG_DIR/inbox_processor.log 2>&1"

# 21:00 每周日 - Axiom Synthesizer：蒸馏公理 + 更新认知地图
CRON_SYNTH="0 21 * * 0   cd $ROOT && PYTHONPATH=$ROOT $PYTHON agents/axiom_synthesizer/synthesizer.py >> $LOG_DIR/synthesizer.log 2>&1"

# ── 写入 crontab（幂等，先清除旧条目）────────────────────────────
TMPFILE=$(mktemp)

crontab -l 2>/dev/null | grep -v -E \
    "bouncer\.py|inbox_processor\.py|daily_briefing\.py|synthesizer\.py" \
    > "$TMPFILE" || true

echo "$CRON_BRIEFING" >> "$TMPFILE"
echo "$CRON_BOUNCER"  >> "$TMPFILE"
echo "$CRON_INBOX"    >> "$TMPFILE"
echo "$CRON_SYNTH"    >> "$TMPFILE"

crontab "$TMPFILE"
rm "$TMPFILE"

echo "✅ Cron 任务已安装："
echo ""
echo "   07:50  Daily Briefing       Telegram 早报推送"
echo "   08:00  Cognitive Bouncer    RSS 扫描 + 评分 → Inbox"
echo "   10:30  Inbox Processor      NotebookLM 合成 + 归档"
echo "   21:00  Axiom Synthesizer    每周日，蒸馏公理 → 认知地图"
echo ""
echo "📋 验证：crontab -l"
echo "📋 日志：tail -f $LOG_DIR/bouncer.log"
