"""
generate_report.py ── Antigravity OS 静态 HTML 报告生成器 (方案 B)

用法：
  python scripts/generate_report.py              # 生成并自动打开
  python scripts/generate_report.py --no-open   # 只生成，不打开浏览器
  python scripts/generate_report.py --out /tmp/report.html
"""

import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.stats import collect, StatsReport

DEFAULT_OUT = _ROOT / "data" / "dashboard.html"


# ── HTML 模板 ────────────────────────────────────────────────────

def render_html(r: StatsReport) -> str:
    days  = list(r.daily_inbox.keys())
    inbox_vals = list(r.daily_inbox.values())
    done_vals  = list(r.daily_done.values())

    # 分数分布饼图数据
    score_labels  = ["9-10 💎", "8-9 🥇", "7-8 ⭐", "<7 🗑️"]
    score_values  = [r.score_dist.get(k, 0) for k in ["9-10","8-9","7-8","<7"]]
    score_colors  = ["#4ade80","#60a5fa","#facc15","#f87171"]

    # pending 笔记表格行
    pending_rows = sorted(
        [n for n in r.notes if n.status == "pending"],
        key=lambda n: n.score, reverse=True
    )[:15]

    def score_badge(score):
        if score >= 9.5: cls, icon = "badge-diamond", "💎"
        elif score >= 9: cls, icon = "badge-gold",    "🏆"
        elif score >= 8.5: cls, icon = "badge-silver","🥇"
        else:             cls, icon = "badge-bronze", "⭐"
        return f'<span class="badge {cls}">{icon} {score:.1f}</span>'

    pending_html = ""
    for n in pending_rows:
        from urllib.parse import urlparse
        host  = urlparse(n.source).netloc if n.source else "─"
        title = (n.title or n.filename)[:55]
        link  = f'<a href="{n.source}" target="_blank">{title}</a>' if n.source else title
        pending_html += f"""
        <tr>
          <td>{score_badge(n.score)}</td>
          <td class="note-title">{link}</td>
          <td class="note-host">{host}</td>
          <td class="note-date">{n.created[:10] if n.created else '─'}</td>
          <td>{'✂️ Clip' if n.is_clip else '🤖 RSS'}</td>
        </tr>"""

    # 健康度颜色
    hc = "#4ade80" if r.health_score >= 80 else "#facc15" if r.health_score >= 50 else "#f87171"

    # pipeline funnel 计算
    funnel_total   = r.total or 1
    pct_done    = r.done    / funnel_total * 100
    pct_pending = r.pending / funnel_total * 100
    pct_error   = r.error   / funnel_total * 100

    def fmt_dt(dt):
        if not dt: return '<span class="na">从未运行</span>'
        delta = datetime.now() - dt
        h = delta.total_seconds() / 3600
        color = "#4ade80" if h < 25 else "#f87171"
        return f'<span style="color:{color}">{dt.strftime("%m-%d %H:%M")} <small>({h:.0f}h 前)</small></span>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Antigravity OS — Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  :root {{
    --bg:      #0f1117;
    --surface: #1a1d27;
    --border:  #2a2d3e;
    --text:    #e2e8f0;
    --dim:     #64748b;
    --accent:  #60a5fa;
    --green:   #4ade80;
    --yellow:  #facc15;
    --red:     #f87171;
    --purple:  #c084fc;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg); color: var(--text);
    font-family: 'Inter', 'SF Pro Text', -apple-system, sans-serif;
    font-size: 14px; line-height: 1.6; padding: 24px;
  }}
  h1 {{ font-size: 22px; font-weight: 700; color: var(--accent); }}
  h2 {{ font-size: 13px; font-weight: 600; color: var(--dim);
        text-transform: uppercase; letter-spacing: .08em; margin-bottom: 14px; }}
  .header {{ display: flex; align-items: center; justify-content: space-between;
             margin-bottom: 24px; }}
  .header-meta {{ color: var(--dim); font-size: 12px; text-align: right; }}

  /* 网格 */
  .grid-3 {{ display: grid; grid-template-columns: repeat(3,1fr); gap: 16px; margin-bottom: 16px; }}
  .grid-2 {{ display: grid; grid-template-columns: repeat(2,1fr); gap: 16px; margin-bottom: 16px; }}
  .grid-4 {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; margin-bottom: 16px; }}

  /* 卡片 */
  .card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 20px;
  }}
  .card.accent-border {{ border-color: var(--accent); }}

  /* KPI 数字 */
  .kpi {{ text-align: center; }}
  .kpi .value {{ font-size: 36px; font-weight: 800; line-height: 1.1; }}
  .kpi .label {{ color: var(--dim); font-size: 12px; margin-top: 4px; }}
  .green {{ color: var(--green); }}
  .yellow {{ color: var(--yellow); }}
  .red {{ color: var(--red); }}
  .accent {{ color: var(--accent); }}

  /* 健康度 */
  .health-ring {{
    width: 120px; height: 120px; margin: 0 auto 12px;
    border-radius: 50%;
    background: conic-gradient({hc} {r.health_score:.0f}%, var(--border) 0);
    display: flex; align-items: center; justify-content: center;
    position: relative;
  }}
  .health-ring::after {{
    content: ''; position: absolute;
    width: 88px; height: 88px; border-radius: 50%;
    background: var(--surface);
  }}
  .health-score {{ position: relative; z-index: 1; font-size: 26px; font-weight: 800;
                   color: {hc}; }}

  /* 漏斗条 */
  .funnel-bar {{ margin-bottom: 10px; }}
  .funnel-label {{ display: flex; justify-content: space-between;
                   font-size: 12px; color: var(--dim); margin-bottom: 4px; }}
  .funnel-track {{ background: var(--border); border-radius: 4px; height: 8px; overflow: hidden; }}
  .funnel-fill {{ height: 8px; border-radius: 4px; transition: width .3s; }}

  /* 表格 */
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ color: var(--dim); font-size: 11px; text-transform: uppercase;
        letter-spacing: .06em; padding: 6px 8px; text-align: left;
        border-bottom: 1px solid var(--border); }}
  td {{ padding: 8px 8px; border-bottom: 1px solid var(--border);
        vertical-align: middle; font-size: 13px; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: rgba(255,255,255,.03); }}
  .note-title a {{ color: var(--text); text-decoration: none; }}
  .note-title a:hover {{ color: var(--accent); }}
  .note-host {{ color: var(--dim); font-size: 12px; }}
  .note-date {{ color: var(--dim); font-size: 12px; }}

  /* Badge */
  .badge {{ border-radius: 5px; padding: 2px 7px; font-size: 12px; font-weight: 600; }}
  .badge-diamond {{ background: #052e16; color: #4ade80; }}
  .badge-gold    {{ background: #1c1917; color: #fbbf24; }}
  .badge-silver  {{ background: #0c1a2e; color: #60a5fa; }}
  .badge-bronze  {{ background: #1c1917; color: #d1d5db; }}

  .na {{ color: var(--dim); }}
  canvas {{ max-height: 220px; }}

  .bottleneck {{
    background: rgba(248,113,113,.08); border: 1px solid rgba(248,113,113,.25);
    border-radius: 8px; padding: 10px 14px; font-size: 13px;
    color: var(--red); margin-top: 10px;
  }}
  .bottleneck.ok {{
    background: rgba(74,222,128,.08); border-color: rgba(74,222,128,.25);
    color: var(--green);
  }}
</style>
</head>
<body>

<!-- HEADER -->
<div class="header">
  <div>
    <h1>🚀 Antigravity OS</h1>
    <p style="color:var(--dim); font-size:12px; margin-top:2px;">
      Information Filtering &amp; Knowledge Pipeline Dashboard
    </p>
  </div>
  <div class="header-meta">
    生成时间：{r.generated_at}<br>
    <a href="https://github.com/huanghuiqiang/AntigravityOS"
       style="color:var(--accent); text-decoration:none; font-size:11px;">
      github.com/huanghuiqiang/AntigravityOS
    </a>
  </div>
</div>

<!-- ROW 1：KPI + 健康度 -->
<div class="grid-4">
  <div class="card kpi">
    <div class="value accent">{r.total}</div>
    <div class="label">📥 总入库</div>
  </div>
  <div class="card kpi">
    <div class="value yellow">{r.pending}</div>
    <div class="label">⏳ Pending</div>
  </div>
  <div class="card kpi">
    <div class="value green">{r.done}</div>
    <div class="label">✅ 已完成</div>
  </div>
  <div class="card kpi">
    <div class="value red">{r.error}</div>
    <div class="label">❌ Error</div>
  </div>
</div>

<!-- ROW 2：健康度 + 漏斗 + Cron -->
<div class="grid-3">

  <!-- 健康度 -->
  <div class="card" style="text-align:center;">
    <h2>系统健康度</h2>
    <div class="health-ring">
      <span class="health-score">{r.health_score:.0f}</span>
    </div>
    <div class="{'bottleneck ok' if r.health_score >= 80 else 'bottleneck'}">
      {r.bottleneck}
    </div>
  </div>

  <!-- Pipeline 漏斗 -->
  <div class="card">
    <h2>Pipeline 漏斗</h2>
    <div class="funnel-bar">
      <div class="funnel-label"><span>📥 入库 {r.total} 条</span><span>100%</span></div>
      <div class="funnel-track"><div class="funnel-fill" style="width:100%;background:var(--accent)"></div></div>
    </div>
    <div class="funnel-bar">
      <div class="funnel-label"><span>✅ 完成 {r.done} 条</span><span>{pct_done:.0f}%</span></div>
      <div class="funnel-track"><div class="funnel-fill" style="width:{pct_done:.0f}%;background:var(--green)"></div></div>
    </div>
    <div class="funnel-bar">
      <div class="funnel-label"><span>⏳ 待处理 {r.pending} 条</span><span>{pct_pending:.0f}%</span></div>
      <div class="funnel-track"><div class="funnel-fill" style="width:{pct_pending:.0f}%;background:var(--yellow)"></div></div>
    </div>
    <div class="funnel-bar">
      <div class="funnel-label"><span>❌ 失败 {r.error} 条</span><span>{pct_error:.0f}%</span></div>
      <div class="funnel-track"><div class="funnel-fill" style="width:{pct_error:.0f}%;background:var(--red)"></div></div>
    </div>
    <div style="margin-top:16px; border-top:1px solid var(--border); padding-top:12px;">
      <div style="display:flex;justify-content:space-between; font-size:12px; color:var(--dim);">
        <span>✂️ 今日 Clip</span>
        <span style="color:var(--text); font-weight:700;">{r.clips_today}</span>
      </div>
    </div>
  </div>

  <!-- Cron 状态 -->
  <div class="card">
    <h2>Cron 状态</h2>
    <table>
      <tr>
        <td style="color:var(--dim);">🤖 Bouncer</td>
        <td>{fmt_dt(r.last_bouncer_run)}</td>
      </tr>
      <tr>
        <td style="color:var(--dim);">🧠 InboxProc</td>
        <td>{fmt_dt(r.last_inbox_run)}</td>
      </tr>
    </table>
    <div style="margin-top:16px;">
      <div style="font-size:11px; color:var(--dim); margin-bottom:6px;">7 天趋势</div>
      <canvas id="sparkChart"></canvas>
    </div>
  </div>

</div>

<!-- ROW 3：折线图 + 分数饼图 -->
<div class="grid-2">
  <div class="card">
    <h2>7 天入库 vs 完成趋势</h2>
    <canvas id="trendChart"></canvas>
  </div>
  <div class="card">
    <h2>分数区间分布</h2>
    <canvas id="scoreChart"></canvas>
  </div>
</div>

<!-- ROW 4：Pending 队列 -->
<div class="card">
  <h2>⏳ Pending 队列（高分优先）</h2>
  {"<p style='color:var(--dim); padding:12px 0;'>当前无 pending 条目 ✅</p>" if not pending_rows else f"""
  <table>
    <thead>
      <tr>
        <th>得分</th><th>标题</th><th>来源</th><th>日期</th><th>类型</th>
      </tr>
    </thead>
    <tbody>
      {pending_html}
    </tbody>
  </table>"""}
</div>

<!-- CHARTS JS -->
<script>
const DAYS  = {json.dumps([d[-5:] for d in days])};
const INBOX = {json.dumps(inbox_vals)};
const DONE  = {json.dumps(done_vals)};

// 趋势折线图
new Chart(document.getElementById('trendChart'), {{
  type: 'bar',
  data: {{
    labels: DAYS,
    datasets: [
      {{
        label: '入库',
        data: INBOX,
        backgroundColor: 'rgba(96,165,250,0.3)',
        borderColor:     '#60a5fa',
        borderWidth: 2, borderRadius: 4,
        type: 'bar',
      }},
      {{
        label: '完成',
        data: DONE,
        borderColor:  '#4ade80',
        backgroundColor: 'rgba(74,222,128,0.15)',
        borderWidth: 2, fill: true,
        type: 'line', tension: 0.3,
        pointRadius: 4, pointBackgroundColor: '#4ade80',
      }},
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: true,
    plugins: {{ legend: {{ labels: {{ color: '#94a3b8' }} }} }},
    scales: {{
      x: {{ ticks: {{ color: '#64748b' }}, grid: {{ color: '#1e293b' }} }},
      y: {{ ticks: {{ color: '#64748b' }}, grid: {{ color: '#1e293b' }}, beginAtZero: true }},
    }}
  }}
}});

// 分数饼图
new Chart(document.getElementById('scoreChart'), {{
  type: 'doughnut',
  data: {{
    labels: {json.dumps(score_labels)},
    datasets: [{{ data: {json.dumps(score_values)},
      backgroundColor: {json.dumps(score_colors)},
      borderWidth: 0, hoverOffset: 8,
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: true,
    plugins: {{
      legend: {{
        position: 'right',
        labels: {{ color: '#94a3b8', boxWidth: 12, padding: 12 }}
      }}
    }}
  }}
}});

// 7天 sparkline 迷你图（bar）
new Chart(document.getElementById('sparkChart'), {{
  type: 'bar',
  data: {{
    labels: DAYS,
    datasets: [
      {{ label:'入库', data: INBOX, backgroundColor:'rgba(96,165,250,0.5)', borderRadius:3 }},
      {{ label:'完成', data: DONE,  backgroundColor:'rgba(74,222,128,0.5)',  borderRadius:3 }},
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: true,
    plugins: {{ legend: {{ labels: {{ color:'#94a3b8', boxWidth:10 }} }} }},
    scales: {{
      x: {{ ticks: {{ color:'#475569', font:{{ size:10 }} }}, grid: {{ display:false }} }},
      y: {{ display: false, beginAtZero: true }},
    }}
  }}
}});
</script>
</body>
</html>"""


# ── 入口 ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="生成 Antigravity OS HTML 报告")
    parser.add_argument("--out",       default=str(DEFAULT_OUT), help="输出路径")
    parser.add_argument("--no-open",   action="store_true",      help="不自动打开浏览器")
    args = parser.parse_args()

    print("📊 收集数据中...")
    r = collect()

    print("🎨 生成 HTML 报告...")
    html = render_html(r)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"✅ 报告已生成: {out}")

    if not args.no_open:
        subprocess.run(["open", str(out)], check=False)
        print("🌐 已在浏览器中打开")


if __name__ == "__main__":
    main()
