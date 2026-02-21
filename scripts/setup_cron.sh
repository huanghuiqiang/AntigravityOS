#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# Antigravity OS | Cron 流水线
#
# 安装方法：
#   chmod +x scripts/setup_cron.sh && ./scripts/setup_cron.sh
#
# 流水线调度：
#   08:00 - Cognitive Bouncer   (RSS 抓取 + 评分 + 写入 Inbox)
#   10:30 - Inbox Processor     (NotebookLM 合成 + 归档 + 通知)
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

# ── 构建 cron 内容 ────────────────────────────────────────────────
CRON_BOUNCER="0 8 * * * cd $ROOT && PYTHONPATH=$ROOT $PYTHON agents/cognitive_bouncer/bouncer.py >> $LOG_DIR/bouncer.log 2>&1"
CRON_INBOX="30 10 * * * cd $ROOT && PYTHONPATH=$ROOT $PYTHON agents/inbox_processor/inbox_processor.py >> $LOG_DIR/inbox_processor.log 2>&1"

# ── 写入 crontab（幂等，不重复添加）─────────────────────────────
TMPFILE=$(mktemp)
crontab -l 2>/dev/null | grep -v "bouncer.py\|inbox_processor.py" > "$TMPFILE" || true

echo "$CRON_BOUNCER"   >> "$TMPFILE"
echo "$CRON_INBOX"     >> "$TMPFILE"

crontab "$TMPFILE"
rm "$TMPFILE"

echo ""
echo "✅ Cron 任务已安装："
echo "   08:00 → Cognitive Bouncer    (RSS 扫描 + 评分)"
echo "   10:30 → Inbox Processor      (NotebookLM + 归档)"
echo ""
echo "📋 验证安装：crontab -l"
echo "📋 查看日志：tail -f $LOG_DIR/bouncer.log"
