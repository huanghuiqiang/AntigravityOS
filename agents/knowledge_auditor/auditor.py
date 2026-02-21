"""
auditor.py
──────────────────────────────────────────────────────────────────
Antigravity OS  |  Knowledge Auditor Agent
"""

import re
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Set

from agos.config import vault_path, backlog_threshold_days
from agos.frontmatter import parse_frontmatter
from agos.notify import send_message

# ── 配置 ─────────────────────────────────────────────────────────
INBOX_FOLDER = "00_Inbox"
BACKLOG_THRESHOLD_DAYS = backlog_threshold_days()

# ── 核心逻辑 ──────────────────────────────────────────────────────

class Auditor:
    def __init__(self, vault: Path = None):
        self.vault_path = vault or vault_path()
        self.all_files = list(self.vault_path.rglob("*.md"))
        self.all_files = [f for f in self.all_files if not any(part.startswith(".") for part in f.parts)]
        self.link_map: Dict[str, Set[str]] = {}
        self._build_link_map()

    def _build_link_map(self):
        for f in self.all_files:
            self.link_map[f.stem] = set()
        link_pattern = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
        for f in self.all_files:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                links = link_pattern.findall(content)
                for link in links:
                    link = link.strip()
                    if link in self.link_map:
                        self.link_map[link].add(f.stem)
            except Exception:
                continue

    def audit_orphans(self) -> List[str]:
        orphans = []
        for name, sources in self.link_map.items():
            if name.startswith("Axiom -"):
                real_sources = {s for s in sources if "认知架构地图" not in s}
                if not real_sources:
                    orphans.append(name)
        return sorted(orphans)

    def audit_backlog(self) -> List[Dict]:
        backlog = []
        limit_date = datetime.now() - timedelta(days=BACKLOG_THRESHOLD_DAYS)
        inbox_path = self.vault_path / INBOX_FOLDER
        for f in inbox_path.rglob("*.md"):
            try:
                content = f.read_text()
                fm, _ = parse_frontmatter(content)
                if fm.get("status") == "pending":
                    created_dt = datetime.strptime(str(fm.get("created", "")), "%Y-%m-%d")
                    if created_dt < limit_date:
                        backlog.append({
                            "title": fm.get("title", f.stem),
                            "days": (datetime.now() - created_dt).days,
                            "score": fm.get("score", 0),
                        })
            except Exception:
                continue
        return sorted(backlog, key=lambda x: x["days"], reverse=True)

    def audit_metadata(self) -> List[str]:
        issues = []
        for f in self.all_files:
            if INBOX_FOLDER not in str(f) and f.parent != self.vault_path:
                continue
            try:
                fm, _ = parse_frontmatter(f.read_text())
                if fm.get("status") == "done":
                    if not fm.get("tags") or not fm.get("source"):
                        issues.append(f.stem)
            except Exception:
                continue
        return issues


def run_audit(silent: bool = False, alert_only: bool = False):
    auditor = Auditor()
    orphans = auditor.audit_orphans()
    backlog = auditor.audit_backlog()
    meta_issues = auditor.audit_metadata()

    score = 100.0
    score -= min(15, len(orphans) * 2)
    score -= min(30, len(backlog) * 5)
    score -= min(10, len(meta_issues) * 1)
    score = max(0, score)

    if alert_only and score > 60 and len(backlog) < 5:
        return

    header = "🚨 <b>Antigravity 知识库紧急警报</b>" if alert_only else "🛡 <b>Antigravity Vault 知识审计周报</b>"
    report = [
        header,
        f"当前健康度: <b>{score:.0f}/100</b>\n",
    ]

    if orphans:
        report.append(f"🕸 <b>知识孤岛 ({len(orphans)})</b>\n<i>建议挑选以下 Axiom 进行编织：</i>")
        report.extend([f"  • {o}" for o in orphans[:5]])
        if len(orphans) > 5:
            report.append(f"  ...等 {len(orphans) - 5} 条")
        report.append("")

    if backlog:
        report.append(f"⏳ <b>积压预警 ({len(backlog)})</b>\n<i>以下笔记已在 Inbox 停留超过 {BACKLOG_THRESHOLD_DAYS} 天：</i>")
        report.extend([f"  • [{b['score']:.1f}] {b['title'][:40]} ({b['days']}d)" for b in backlog[:5]])
        report.append("")

    if not silent:
        send_message("\n".join(report))
    else:
        print("\n".join(report).replace("<b>", "").replace("</b>", ""))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--alert", action="store_true", help="仅在健康度低时报警")
    args = parser.parse_args()
    run_audit(silent=args.silent, alert_only=args.alert)
