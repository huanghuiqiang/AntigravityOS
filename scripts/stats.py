"""
stats.py ── Antigravity OS 数据收集共享层
A/B 两种仪表盘都从这里读数据，保持逻辑统一。
"""

import re
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from typing import Optional

from agos.config import (
    project_root,
    vault_path,
    inbox_folder,
    inbox_path,
    bouncer_log_file,
    inbox_processor_log_file,
)
from agos.frontmatter import parse_frontmatter

# ── 路径 ─────────────────────────────────────────────────────────
ROOT = project_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VAULT = vault_path()
INBOX_DIR = inbox_path()
INBOX_FOLDER = inbox_folder()
BOUNCER_LOG = bouncer_log_file()
INBOX_LOG = inbox_processor_log_file()


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
    clips_today: int = 0

    score_dist:  dict = field(default_factory=dict)
    daily_inbox: dict = field(default_factory=dict)
    daily_done:  dict = field(default_factory=dict)

    # ── Cron 历史 ─────────────────────────────────────────────────
    last_bouncer_run:   Optional[datetime] = None
    last_inbox_run:     Optional[datetime] = None
    bouncer_7day:       list = field(default_factory=list)
    throughput_7day:    list = field(default_factory=list)

    # ── 系统健康 ─────────────────────────────────────────────────
    health_score:   float = 0.0
    bottleneck:     str   = ""
    generated_at:   str   = ""

    # ── 审计数据 (Knowledge Auditor) ─────────────────────────────
    orphan_axioms:  list[str] = field(default_factory=list)
    backlog_issues: list[dict] = field(default_factory=list)
    meta_issues:    list[str] = field(default_factory=list)


# ── 内部工具 ──────────────────────────────────────────────────────
def _warn(scope: str, detail: str, err: Exception | None = None):
    if err is None:
        print(f"  ⚠️ [{scope}] {detail}")
    else:
        print(f"  ⚠️ [{scope}] {detail}: {err}")

def _parse_bouncer_log() -> list[CronRun]:
    """从 bouncer.log 提取历史运行记录。"""
    runs = []
    if not BOUNCER_LOG.exists():
        return runs

    content = BOUNCER_LOG.read_text(encoding="utf-8", errors="ignore")
    scanned_re = re.compile(r"(?:本次)?共审查\s*(\d+)\s*篇")
    golden_re  = re.compile(r"高认知密度文章:\s*(\d+)")

    try:
        mtime = datetime.fromtimestamp(BOUNCER_LOG.stat().st_mtime)
        scanned_match = scanned_re.search(content)
        golden_match = golden_re.search(content)
        scanned = int(scanned_match.group(1)) if scanned_match else 0
        golden = int(golden_match.group(1)) if golden_match else 0
        runs.append(CronRun(agent="bouncer", time=mtime, scanned=scanned, golden=golden))
    except Exception as e:
        _warn("stats/bouncer_log", f"解析日志失败: {BOUNCER_LOG}", e)
    return runs


def _parse_inbox_log() -> list[CronRun]:
    runs = []
    if not INBOX_LOG.exists():
        return runs
    try:
        mtime = datetime.fromtimestamp(INBOX_LOG.stat().st_mtime)
        runs.append(CronRun(agent="inbox_processor", time=mtime))
    except Exception as e:
        _warn("stats/inbox_log", f"解析日志失败: {INBOX_LOG}", e)
    return runs


# ── 主收集函数 ────────────────────────────────────────────────────

def collect() -> StatsReport:
    report = StatsReport(generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    today_str = datetime.now().strftime("%Y-%m-%d")

    # ── 1. 扫描 Inbox 笔记 ────────────────────────────────────────
    notes: list[NoteRecord] = []

    def _scan_dir(d: Path):
        for f in d.iterdir():
            if f.is_dir():
                _scan_dir(f)
            elif f.suffix == ".md":
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    fm, _ = parse_frontmatter(content)
                    if not fm:
                        _warn("stats/scan_note", f"frontmatter 缺失，跳过: {f}")
                        continue

                    tags = fm.get("tags", [])
                    if isinstance(tags, str):
                        tags = [tags]
                    if not any(t in tags for t in ["BouncerDump", "WebClip", "PDFIngested"]):
                        continue

                    notes.append(NoteRecord(
                        filename=f.name,
                        status=str(fm.get("status", "unknown")),
                        score=float(fm.get("score", 0)),
                        source=str(fm.get("source", "")),
                        title=str(fm.get("title", f.stem)),
                        created=str(fm.get("created", "")),
                        processed_at=str(fm.get("processed_at", "")),
                        tags=tags,
                        is_clip="WebClip" in tags,
                    ))
                except Exception as e:
                    _warn("stats/scan_note", f"解析失败: {f}", e)

    if INBOX_DIR.exists():
        _scan_dir(INBOX_DIR)

    report.notes = notes
    report.total = len(notes)

    # ── 2. 状态统计 ───────────────────────────────────────────────
    status_counter = Counter(n.status for n in notes)
    report.pending = status_counter.get("pending", 0)
    report.done = status_counter.get("done", 0)
    report.error = status_counter.get("error", 0)
    report.clips_today = sum(1 for n in notes if n.is_clip and n.created == today_str)

    # ── 3. 分数分布 ───────────────────────────────────────────────
    buckets = {"9-10": 0, "8-9": 0, "7-8": 0, "<7": 0}
    for n in notes:
        s = n.score
        if s >= 9:    buckets["9-10"] += 1
        elif s >= 8:  buckets["8-9"] += 1
        elif s >= 7:  buckets["7-8"] += 1
        else:         buckets["<7"] += 1
    report.score_dist = buckets

    # ── 4. 每日入库趋势（最近 7 天）─────────────────────────────
    days7 = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
    daily_inbox = defaultdict(int)
    daily_done = defaultdict(int)
    for n in notes:
        if n.created in days7:
            daily_inbox[n.created] += 1
        if n.processed_at and n.processed_at[:10] in days7:
            daily_done[n.processed_at[:10]] += 1

    report.bouncer_7day = [daily_inbox[d] for d in days7]
    report.throughput_7day = [daily_done[d] for d in days7]

    # ── 5. Cron 最后运行时间 ──────────────────────────────────────
    bouncer_runs = _parse_bouncer_log()
    inbox_runs = _parse_inbox_log()
    if bouncer_runs:
        report.last_bouncer_run = bouncer_runs[-1].time
    if inbox_runs:
        report.last_inbox_run = inbox_runs[-1].time

    # ── 6. 运行 Knowledge Auditor ──────────────────────────────
    try:
        from agents.knowledge_auditor.auditor import Auditor
        auditor = Auditor(VAULT)
        report.orphan_axioms = auditor.audit_orphans()
        report.backlog_issues = auditor.audit_backlog()
        report.meta_issues = auditor.audit_metadata()
    except Exception as e:
        print(f"  ⚠️ Auditor integration failed: {e}")

    # ── 7. 系统健康评分 ──────────────────────────────────────────
    health = 100.0
    bottlenecks = []

    if report.total > 0:
        err_rate = report.error / report.total
        if err_rate > 0.1:
            health -= 20
            bottlenecks.append(f"❌ Error 率 {err_rate:.0%}")

    if report.pending > 20:
        health -= 15
        bottlenecks.append(f"⏳ Pending 积压 {report.pending} 条")

    if report.orphan_axioms:
        penalty = min(15, len(report.orphan_axioms) * 2)
        health -= penalty
        bottlenecks.append(f"🕸 知识孤岛 ({len(report.orphan_axioms)})")

    if report.last_bouncer_run:
        idle_h = (datetime.now() - report.last_bouncer_run).total_seconds() / 3600
        if idle_h > 26:
            health -= 20
            bottlenecks.append(f"🔇 Bouncer 已 {idle_h:.0f}h 未运行")

    report.health_score = max(0.0, health)
    report.bottleneck = bottlenecks[0] if bottlenecks else "✅ 系统运行正常"

    return report


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    report = collect()
    print(json.dumps(report.__dict__, indent=4, default=str))
