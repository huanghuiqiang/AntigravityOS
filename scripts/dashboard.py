"""
dashboard.py ── Antigravity OS 终端仪表盘 (方案 A)

用法：
  python scripts/dashboard.py            # 单次输出
  python scripts/dashboard.py --watch    # 每 30s 刷新
  python scripts/dashboard.py --watch --interval 10
"""

import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.stats import collect, StatsReport

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.text import Text
    from rich.live import Live
    from rich.layout import Layout
    from rich import box
    from rich.progress import Progress, BarColumn, TextColumn
    from rich.rule import Rule
    from rich.align import Align
except ImportError:
    print("安装 rich: pip install rich")
    sys.exit(1)

console = Console()

# ── 颜色/Emoji 工具 ───────────────────────────────────────────────

def health_color(score: float) -> str:
    if score >= 80: return "green"
    if score >= 50: return "yellow"
    return "red"

def score_emoji(score: float) -> str:
    if score >= 9.5: return "💎"
    if score >= 9.0: return "🏆"
    if score >= 8.5: return "🥇"
    if score >= 8.0: return "⭐"
    return "🗑️"

def sparkline(values: list[int], width: int = 7) -> str:
    """将整数列表渲染为迷你折线（使用 Unicode 块字符）。"""
    bars = " ▁▂▃▄▅▆▇█"
    if not values or max(values) == 0:
        return "─" * width
    m = max(values)
    return "".join(bars[min(int(v / m * 8), 8)] for v in values)


# ── 各面板构建函数 ────────────────────────────────────────────────

def build_health_panel(r: StatsReport) -> Panel:
    color = health_color(r.health_score)
    bar_filled = int(r.health_score / 100 * 20)
    bar = f"[{color}]{'█' * bar_filled}[/{color}]{'░' * (20 - bar_filled)}"

    text = Text()
    text.append(f"  系统健康度  ", style="bold white")
    text.append(f"{r.health_score:.0f}/100\n", style=f"bold {color}")
    text.append(f"  {bar}\n\n")
    text.append(f"  当前瓶颈：{r.bottleneck}\n", style="dim")
    text.append(f"  数据截止：{r.generated_at}", style="dim")

    return Panel(text, title="[bold cyan]🚀 Antigravity OS[/bold cyan]",
                 border_style="cyan", expand=True)


def build_pipeline_table(r: StatsReport) -> Panel:
    tbl = Table(box=box.SIMPLE, show_header=False, expand=True)
    tbl.add_column("指标", style="bold")
    tbl.add_column("值",   justify="right")
    tbl.add_column("",     width=2)

    tbl.add_row("📥 总入库",  str(r.total),   "")
    tbl.add_row("⏳ Pending",
                f"[yellow]{r.pending}[/yellow]",
                "⚠️" if r.pending > 20 else "")
    tbl.add_row("✅ Done",
                f"[green]{r.done}[/green]", "")
    tbl.add_row("❌ Error",
                f"[red]{r.error}[/red]",
                "🔴" if r.error > 0 else "")
    tbl.add_row("─" * 10, "─" * 5, "")
    tbl.add_row("✂️ 今日 Clip", str(r.clips_today), "")

    # 漏斗率
    if r.total > 0:
        rate = f"{r.done / r.total * 100:.0f}%"
        tbl.add_row("📊 完成率", f"[cyan]{rate}[/cyan]", "")

    return Panel(tbl, title="[bold]Pipeline 状态[/bold]", border_style="blue")


def build_score_panel(r: StatsReport) -> Panel:
    dist  = r.score_dist
    total = sum(dist.values()) or 1

    tbl = Table(box=box.SIMPLE, show_header=False, expand=True)
    tbl.add_column("区间", style="bold")
    tbl.add_column("数量", justify="right")
    tbl.add_column("占比条", width=14)

    colors = {"9-10": "green", "8-9": "cyan", "7-8": "yellow", "<7": "red"}
    emojis = {"9-10": "💎", "8-9": "🥇", "7-8": "⭐", "<7": "🗑️"}

    for band, color in colors.items():
        cnt   = dist.get(band, 0)
        width = int(cnt / total * 12)
        bar   = f"[{color}]{'█' * width}[/{color}]{'░' * (12 - width)}"
        pct   = f"{cnt/total*100:.0f}%"
        tbl.add_row(f"{emojis[band]} {band}", f"{cnt} ({pct})", bar)

    return Panel(tbl, title="[bold]📊 分数分布[/bold]", border_style="magenta")


def build_cron_panel(r: StatsReport) -> Panel:
    def fmt_time(dt) -> str:
        if not dt:
            return "[red]从未运行[/red]"
        delta = datetime.now() - dt
        h = delta.total_seconds() / 3600
        color = "green" if h < 25 else "red"
        return f"[{color}]{dt.strftime('%m-%d %H:%M')} ({h:.0f}h 前)[/{color}]"

    tbl = Table(box=box.SIMPLE, show_header=False, expand=True)
    tbl.add_column("Agent", style="bold")
    tbl.add_column("最后运行")

    tbl.add_row("🤖 Bouncer",        fmt_time(r.last_bouncer_run))
    tbl.add_row("🧠 InboxProcessor", fmt_time(r.last_inbox_run))

    # 7天趋势迷你图
    spark_in   = sparkline(r.bouncer_7day)
    spark_done = sparkline(r.throughput_7day)
    tbl.add_row("─" * 12, "─" * 15)
    tbl.add_row("📈 入库 7d",  f"[cyan]{spark_in}[/cyan]   {sum(r.bouncer_7day)} 条")
    tbl.add_row("✅ 完成 7d",  f"[green]{spark_done}[/green]   {sum(r.throughput_7day)} 条")

    return Panel(tbl, title="[bold]⏰ Cron 状态[/bold]", border_style="yellow")


def build_recent_table(r: StatsReport) -> Panel:
    """最近 8 条 pending 笔记列表（最需要处理的）。"""
    pending = sorted(
        [n for n in r.notes if n.status == "pending"],
        key=lambda n: n.score,
        reverse=True,
    )[:8]

    tbl = Table(box=box.SIMPLE, show_header=True, expand=True)
    tbl.add_column("分", justify="right", width=5)
    tbl.add_column("标题",  max_width=40, no_wrap=True)
    tbl.add_column("来源",  max_width=20, no_wrap=True, style="dim")
    tbl.add_column("日期",  width=10, style="dim")

    if not pending:
        tbl.add_row("─", "[dim]无 pending 条目[/dim]", "", "")
    else:
        for n in pending:
            from urllib.parse import urlparse
            host  = urlparse(n.source).netloc[:18] if n.source else "─"
            title = (n.title or n.filename)[:38]
            tbl.add_row(
                f"[cyan]{n.score:.1f}[/cyan]",
                title,
                host,
                n.created[:10] if n.created else "─",
            )

    return Panel(tbl, title=f"[bold]⏳ Pending 队列（Top {min(8, len(pending))}）[/bold]",
                 border_style="blue")


def build_audit_panel(r: StatsReport) -> Panel:
    """展示 Knowledge Auditor 的扫描结果。"""
    tbl = Table(box=box.SIMPLE, show_header=False, expand=True)
    tbl.add_column("项目", style="bold")
    tbl.add_column("状态",   justify="right")

    # 1. 孤儿公理
    orphans_count = len(r.orphan_axioms)
    color = "red" if orphans_count > 5 else "yellow" if orphans_count > 0 else "green"
    tbl.add_row("🕸 孤儿 Axiom", f"[{color}]{orphans_count}[/{color}]")

    # 2. 积压警报
    backlog_count = len(r.backlog_issues)
    color = "red" if backlog_count > 0 else "green"
    tbl.add_row("⏳ 积压警报 (>10d)", f"[{color}]{backlog_count}[/{color}]")

    # 3. 元数据缺陷
    meta_count = len(r.meta_issues)
    color = "yellow" if meta_count > 0 else "green"
    tbl.add_row("🏷 元数据缺失", f"[{color}]{meta_count}[/{color}]")

    # 详情摘要（如果有孤儿 Axiom，列出前 3 个）
    if r.orphan_axioms:
        tbl.add_row("─" * 12, "─" * 8)
        for name in r.orphan_axioms[:3]:
            short_name = name.replace("Axiom -", "").strip()[:20]
            tbl.add_row(f"  • {short_name}", "", style="dim")
        if len(r.orphan_axioms) > 3:
            tbl.add_row(f"    ...等 {len(r.orphan_axioms)-3} 条", "", style="dim")

    return Panel(tbl, title="[bold]🛡 知识库健康 (Auditor)[/bold]", border_style="white")


# ── 完整仪表盘渲染 ────────────────────────────────────────────────

def render(r: StatsReport):
    console.clear()
    console.print(build_health_panel(r))

    # 中间行：Pipeline + 分数 + Cron + Audit 四列
    console.print(Columns([
        build_pipeline_table(r),
        build_score_panel(r),
        build_cron_panel(r),
        build_audit_panel(r),
    ], expand=True))

    console.print(build_recent_table(r))
    console.print(Rule(style="dim"))
    console.print(
        f"[dim]  刷新时间: {r.generated_at} | "
        f"AntigravityOS · github.com/huanghuiqiang/AntigravityOS[/dim]"
    )


# ── 入口 ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Antigravity OS 终端仪表盘")
    parser.add_argument("--watch",    action="store_true", help="持续刷新模式")
    parser.add_argument("--interval", type=int, default=30, help="刷新间隔（秒，默认30）")
    args = parser.parse_args()

    if args.watch:
        console.print(f"[dim]👀 Watch 模式，每 {args.interval}s 刷新 (Ctrl+C 退出)[/dim]\n")
        while True:
            try:
                r = collect()
                render(r)
                time.sleep(args.interval)
            except KeyboardInterrupt:
                console.print("\n[dim]已退出[/dim]")
                break
    else:
        r = collect()
        render(r)


if __name__ == "__main__":
    main()
