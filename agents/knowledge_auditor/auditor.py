"""
auditor.py
──────────────────────────────────────────────────────────────────
Antigravity OS  |  Knowledge Auditor Agent

职责：
  1. 孤岛检测：找出没有被引用的 Axiom 笔记（孤儿公理）
  2. 积压预警：识别 Inbox 中积压超过 10 天的 pending 笔记
  3. 元数据审计：检查 status: done 但缺失 tags 或 source 的笔记
  4. 汇总报告：通过 Telegram 推送健康体检结果

触发建议：每周一早晨执行
"""

import os
import re
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Set

# ── 路径初始化 ────────────────────────────────────────────────────
_THIS_DIR = Path(__file__).parent
_ROOT     = _THIS_DIR.parent.parent
sys.path.insert(0, str(_ROOT))

from skills.obsidian_bridge.bridge import get_vault, _parse_frontmatter

_BOUNCER_DIR = _ROOT / "agents/cognitive_bouncer"
sys.path.insert(0, str(_BOUNCER_DIR))
from telegram_notify import send_message

# ── 配置 ─────────────────────────────────────────────────────────
VAULT = get_vault()
INBOX_FOLDER = "00_Inbox"
BACKLOG_THRESHOLD_DAYS = 10  # 积压天数阈值

# ── 核心逻辑 ──────────────────────────────────────────────────────

class Auditor:
    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.all_files = list(vault_path.rglob("*.md"))
        self.all_files = [f for f in self.all_files if not any(part.startswith(".") for part in f.parts)]
        
        self.link_map: Dict[str, Set[str]] = {}  # target_name -> sources set (incoming links)
        self._build_link_map()

    def _build_link_map(self):
        """扫描全库建立引用图（Incoming Links）。"""
        # 初项化 map，确保所有 .md 文件都在键中
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
        """找出没有任何引用的 Axiom 笔记（除去 000 认知架构地图的引用）。"""
        orphans = []
        for name, sources in self.link_map.items():
            if name.startswith("Axiom -"):
                # 排除 000 认知架构地图，如果只有它引用，或者完全没引用
                real_sources = {s for s in sources if "认知架构地图" not in s}
                if not real_sources:
                    orphans.append(name)
        return sorted(orphans)

    def audit_backlog(self) -> List[Dict]:
        """识别 Inbox 中长期积压的 pending 笔记。"""
        backlog = []
        limit_date = datetime.now() - timedelta(days=BACKLOG_THRESHOLD_DAYS)
        
        inbox_path = self.vault_path / INBOX_FOLDER
        for f in inbox_path.rglob("*.md"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                fm, _ = _parse_frontmatter(content)
                if fm.get("status") == "pending":
                    created_str = fm.get("created", "")
                    try:
                        created_dt = datetime.strptime(str(created_str), "%Y-%m-%d")
                        if created_dt < limit_date:
                            backlog.append({
                                "title": fm.get("title", f.stem),
                                "days": (datetime.now() - created_dt).days,
                                "score": fm.get("score", 0)
                            })
                    except ValueError:
                        continue
            except Exception:
                continue
        return sorted(backlog, key=lambda x: x["days"], reverse=True)

    def audit_metadata(self) -> List[str]:
        """检查元数据缺失情况。"""
        issues = []
        for f in self.all_files:
            # 只检查 Inbox 或主要层级的 done 笔记
            if INBOX_FOLDER not in str(f) and f.parent != self.vault_path:
                continue
                
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                fm, _ = _parse_frontmatter(content)
                if fm.get("status") == "done":
                    missing = []
                    if not fm.get("tags"): missing.append("tags")
                    if not fm.get("source"): missing.append("source")
                    
                    if missing:
                        issues.append(f"{f.stem} (缺失: {', '.join(missing)})")
            except Exception:
                continue
        return issues

def run_audit(silent: bool = False):
    print("🔍 [Knowledge Auditor] 启动 Vault 深度扫描...")
    auditor = Auditor(VAULT)
    
    orphans = auditor.audit_orphans()
    backlog = auditor.audit_backlog()
    meta_issues = auditor.audit_metadata()
    
    # ── 汇总报告 ──
    report_lines = ["🛡 <b>Antigravity Vault 知识审计报告</b>\n"]
    
    # 1. 孤岛
    if orphans:
        report_lines.append(f"🕸 <b>孤儿 Axiom 检测 ({len(orphans)})</b>")
        report_lines.append("<i>发现以下公理未被项目或主干引用，可能沦为认知冷资产：</i>")
        for o in orphans[:8]:
            report_lines.append(f"  • {o}")
        if len(orphans) > 8:
            report_lines.append(f"  ...等其余 {len(orphans)-8} 条")
        report_lines.append("")
    
    # 2. 积压
    if backlog:
        report_lines.append(f"⏳ <b>Inbox 积压预警 ({len(backlog)})</b>")
        report_lines.append(f"<i>以下 pending 超过 {BACKLOG_THRESHOLD_DAYS} 天，建议清理：</i>")
        for b in backlog[:5]:
            report_lines.append(f"  • [{b['score']:.1f}] {b['title'][:40]} ({b['days']}d)")
        report_lines.append("")

    # 3. 元数据
    if meta_issues:
        report_lines.append(f"🏷 <b>元数据缺失 ({len(meta_issues)})</b>")
        for m in meta_issues[:5]:
            report_lines.append(f"  • {m}")
        report_lines.append("")

    if not orphans and not backlog and not meta_issues:
        report_lines.append("✅ <b>Vault 状态完美，未发现显著亚健康项。</b>")
    
    report_text = "\n".join(report_lines)
    print(report_text.replace("<b>","").replace("</b>","").replace("<i>","").replace("</i>",""))
    
    if not silent:
        send_message(report_text)
    
    return {
        "orphans": len(orphans),
        "backlog": len(backlog),
        "meta_issues": len(meta_issues)
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Antigravity Knowledge Auditor")
    parser.add_argument("--silent", action="store_true", help="不推送 Telegram")
    args = parser.parse_args()
    run_audit(silent=args.silent)
