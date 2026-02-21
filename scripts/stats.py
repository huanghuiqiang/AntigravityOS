"""
stats.py ── Antigravity OS 数据收集共享层
A/B 两种仪表盘都从这里读数据，保持逻辑统一。
"""

import os
import re
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from typing import Optional

# ── 路径 ─────────────────────────────────────────────────────────
_ROOT         = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

VAULT         = Path(os.getenv("OBSIDIAN_VAULT", "/Users/hugh/Documents/Obsidian/AINotes"))
INBOX_DIR     = VAULT / "00_Inbox"
LOG_DIR       = _ROOT / "data" / "logs"
BOUNCER_LOG   = _ROOT / "agents" / "cognitive_bouncer" / "bouncer.log"


# ── 数据结构 ──────────────────────────────────────────────────────

@dataclass
class NoteRecord:
    filename:     str
    status:       str        # pending / done / error / (unknown)
    score:        float
    source:       str
    title:        str
    created:      str        # YYYY-MM-DD
    processed_at: str        # YYYY-MM-DD HH:MM  or ""
    tags:         list[str]
    is_clip:      bool       # True = WebClip, False = Bouncer

@dataclass
class CronRun:
    agent:   str             # bouncer / inbox_processor
    time:    datetime
    scanned: int = 0
    golden:  int = 0
    success: bool = True

@dataclass
class StatsReport:
    # ── Inbox 状态 ────────────────────────────────────────────────
    notes: list[NoteRecord] = field(default_factory=list)

    # ── 聚合指标 ─────────────────────────────────────────────────
    total:       int = 0
    pending:     int = 0
    done:        int = 0
    error:       int = 0
    clips_today: int = 0     # WebClip 今日新增

    score_dist:  dict = field(default_factory=dict)   # {"9-10": 3, "8-9": 9, ...}
    daily_inbox: dict = field(default_factory=dict)   # {"2026-02-21": 5, ...}
    daily_done:  dict = field(default_factory=dict)   # 每日完成数

    # ── Cron 历史 ─────────────────────────────────────────────────
    last_bouncer_run:   Optional[datetime] = None
    last_inbox_run:     Optional[datetime] = None
    bouncer_7day:       list = field(default_factory=list)   # 最近7天每日扫描量
    throughput_7day:    list = field(default_factory=list)   # 最近7天每日completed量

    # ── 系统健康 ─────────────────────────────────────────────────
    health_score:   float = 0.0     # 0-100
    bottleneck:     str   = ""      # 描述当前瓶颈
    generated_at:   str   = ""


# ── 内部工具 ──────────────────────────────────────────────────────

def _parse_frontmatter(content: str) -> dict:
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    import yaml
    try:
        return yaml.safe_load(content[3:end]) or {}
    except Exception:
        return {}


def _parse_bouncer_log() -> list[CronRun]:
    """从 bouncer.log 提取历史运行记录。"""
    runs = []
    if not BOUNCER_LOG.exists():
        return runs

    content = BOUNCER_LOG.read_text(encoding="utf-8", errors="ignore")

    # 匹配日志中的启动行和结果行
    # 格式示例（根据实际日志结构做正则）
    scanned_re = re.compile(r"本次共审查\s*(\d+)\s*篇")
    golden_re  = re.compile(r"高认知密度文章:\s*(\d+)")
    # 用文件 mtime 作为近似时间（更简单可靠）
    try:
        mtime = datetime.fromtimestamp(BOUNCER_LOG.stat().st_mtime)
        scanned = int((scanned_re.search(content) or type('', (), {'group': lambda s, x: '0'})()).group(1))
        golden  = int((golden_re.search(content) or type('', (), {'group': lambda s, x: '0'})()).group(1))
        runs.append(CronRun(agent="bouncer", time=mtime, scanned=scanned, golden=golden))
    except Exception:
        pass

    return runs


def _parse_inbox_log() -> list[CronRun]:
    """从 inbox_processor.log 提取历史。"""
    runs = []
    log_path = LOG_DIR / "inbox_processor.log"
    if not log_path.exists():
        return runs
    try:
        mtime = datetime.fromtimestamp(log_path.stat().st_mtime)
        runs.append(CronRun(agent="inbox_processor", time=mtime))
    except Exception:
        pass
    return runs


# ── 主收集函数 ────────────────────────────────────────────────────

def collect() -> StatsReport:
    report = StatsReport(generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    today  = datetime.now().strftime("%Y-%m-%d")

    # ── 1. 扫描 Inbox 笔记 ────────────────────────────────────────
    notes: list[NoteRecord] = []

    def _scan_dir(d: Path):
        for f in d.iterdir():
            if f.is_dir():
                _scan_dir(f)          # 递归处理日期子文件夹
            elif f.suffix == ".md":
                try:
                    content = f.read_text(encoding="utf-8")
                    fm      = _parse_frontmatter(content)
                    if not fm:
                        continue
                    # 只统计 Bouncer/Clip 产生的笔记
                    tags = fm.get("tags", [])
                    if isinstance(tags, str):
                        tags = [tags]
                    if not any(t in tags for t in ["BouncerDump", "WebClip"]):
                        continue

                    notes.append(NoteRecord(
                        filename     = f.name,
                        status       = str(fm.get("status", "unknown")),
                        score        = float(fm.get("score", 0)),
                        source       = str(fm.get("source", "")),
                        title        = str(fm.get("title", f.stem)),
                        created      = str(fm.get("created", "")),
                        processed_at = str(fm.get("processed_at", "")),
                        tags         = tags,
                        is_clip      = "WebClip" in tags,
                    ))
                except Exception:
                    pass

    if INBOX_DIR.exists():
        _scan_dir(INBOX_DIR)

    report.notes = notes
    report.total = len(notes)

    # ── 2. 状态统计 ───────────────────────────────────────────────
    status_counter = Counter(n.status for n in notes)
    report.pending = status_counter.get("pending", 0)
    report.done    = status_counter.get("done", 0)
    report.error   = status_counter.get("error", 0)
    report.clips_today = sum(
        1 for n in notes if n.is_clip and n.created == today
    )

    # ── 3. 分数分布 ───────────────────────────────────────────────
    buckets = {"9-10": 0, "8-9": 0, "7-8": 0, "<7": 0}
    for n in notes:
        s = n.score
        if s >= 9:    buckets["9-10"] += 1
        elif s >= 8:  buckets["8-9"]  += 1
        elif s >= 7:  buckets["7-8"]  += 1
        else:         buckets["<7"]   += 1
    report.score_dist = buckets

    # ── 4. 每日入库趋势（最近 7 天）─────────────────────────────
    days7 = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
    daily_inbox = defaultdict(int)
    daily_done  = defaultdict(int)
    for n in notes:
        if n.created in days7:
            daily_inbox[n.created] += 1
        if n.processed_at and n.processed_at[:10] in days7:
            daily_done[n.processed_at[:10]] += 1
    report.daily_inbox   = {d: daily_inbox[d] for d in days7}
    report.daily_done    = {d: daily_done[d]  for d in days7}
    report.throughput_7day = [daily_done[d] for d in days7]
    report.bouncer_7day    = [daily_inbox[d] for d in days7]

    # ── 5. Cron 最后运行时间 ──────────────────────────────────────
    bouncer_runs = _parse_bouncer_log()
    inbox_runs   = _parse_inbox_log()
    if bouncer_runs:
        report.last_bouncer_run = bouncer_runs[-1].time
    if inbox_runs:
        report.last_inbox_run = inbox_runs[-1].time

    # ── 6. 系统健康评分（简单规则引擎）──────────────────────────
    health = 100.0
    bottlenecks = []

    # 规则1：error 率超 10% 扣分
    if report.total > 0:
        err_rate = report.error / report.total
        if err_rate > 0.1:
            health -= 20
            bottlenecks.append(f"❌ Error 率 {err_rate:.0%}（>{10}%）")

    # 规则2：pending 积压超 20 条
    if report.pending > 20:
        health -= 15
        bottlenecks.append(f"⏳ Pending 积压 {report.pending} 条")

    # 规则3：Bouncer 超过 25 小时未运行
    if report.last_bouncer_run:
        idle_h = (datetime.now() - report.last_bouncer_run).total_seconds() / 3600
        if idle_h > 25:
            health -= 20
            bottlenecks.append(f"🔇 Bouncer 已 {idle_h:.0f}h 未运行")
    else:
        health -= 10
        bottlenecks.append("🔇 无 Bouncer 运行记录")

    # 规则4：7天内总产出为 0
    if report.total == 0:
        health -= 30
        bottlenecks.append("📭 Inbox 为空，Pipeline 未启动")

    report.health_score = max(0.0, health)
    report.bottleneck   = bottlenecks[0] if bottlenecks else "✅ 系统运行正常"

    return report
