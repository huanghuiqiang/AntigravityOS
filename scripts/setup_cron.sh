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
#   */4h   Auditor Alert       每 4 小时静默健康扫描
#   10:30  Inbox Processor     NotebookLM 合成 + 归档 + 通知
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

# 07:50 - 每日早报（Bouncer 运行前推送昨日摘要 + 审计警报）
CRON_BRIEFING="50 7 * * *  cd $ROOT && PYTHONPATH=$ROOT $PYTHON agents/daily_briefing/daily_briefing.py >> $LOG_DIR/daily_briefing.log 2>&1"

# 08:00 - Cognitive Bouncer：RSS 扫描 + 评分 + 写 Inbox
CRON_BOUNCER="0 8 * * *   cd $ROOT && PYTHONPATH=$ROOT $PYTHON agents/cognitive_bouncer/bouncer.py >> $LOG_DIR/bouncer.log 2>&1"

# 09:00 每周一 - Knowledge Auditor：知识库审计周报
CRON_AUDIT="0 9 * * 1    cd $ROOT && PYTHONPATH=$ROOT $PYTHON agents/knowledge_auditor/auditor.py >> $LOG_DIR/knowledge_auditor.log 2>&1"

# 每 4 小时 - Knowledge Auditor (Alert Mode)：静默巡检，健康度低时报警
CRON_ALERT="0 */4 * * *  cd $ROOT && PYTHONPATH=$ROOT $PYTHON agents/knowledge_auditor/auditor.py --alert >> $LOG_DIR/knowledge_auditor.log 2>&1"

# 10:30 - Inbox Processor：NotebookLM 合成 + 归档 + 通知
CRON_INBOX="30 10 * * *  cd $ROOT && PYTHONPATH=$ROOT $PYTHON agents/inbox_processor/inbox_processor.py >> $LOG_DIR/inbox_processor.log 2>&1"

# Axiom Synthesizer 已改为手动执行（见早报提醒）

# ── 写入 crontab（幂等，先清除旧条目）────────────────────────────
TMPFILE=$(mktemp)

# 清除所有 Antigravity 相关的旧任务
crontab -l 2>/dev/null | grep -v -E \
    "bouncer\.py|inbox_processor\.py|daily_briefing\.py|synthesizer\.py|auditor\.py" \
    > "$TMPFILE" || true

echo "$CRON_BRIEFING" >> "$TMPFILE"
echo "$CRON_BOUNCER"  >> "$TMPFILE"
echo "$CRON_AUDIT"    >> "$TMPFILE"
echo "$CRON_ALERT"    >> "$TMPFILE"
echo "$CRON_INBOX"    >> "$TMPFILE"

crontab "$TMPFILE"
rm "$TMPFILE"

echo "✅ Cron 任务已安装："
echo ""
echo "   07:50  Daily Briefing       Telegram 早报推送 (含合成提醒)"
echo "   08:00  Cognitive Bouncer    RSS 扫描 + 评分 → Inbox"
echo "   */4h   Auditor Alert        静默健康巡检 (亚健康报警)"
echo "   10:30  Inbox Processor      NotebookLM 合成 + 归档"
echo ""
echo "💡 Axiom Synthesizer 已切换为手动模式，请在收到早报提醒后执行。"
echo ""
echo "📋 验证：crontab -l"
echo "📋 日志：tail -f $LOG_DIR/bouncer.log"
