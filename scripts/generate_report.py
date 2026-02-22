"""
generate_report.py ── Antigravity OS 静态 HTML 报告生成器 (方案 B)
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


def render_html(r: StatsReport) -> str:
    days  = [(datetime.now() - timedelta(days=i)).strftime("%m-%d") for i in range(6, -1, -1)]
    inbox_vals = r.bouncer_7day
    done_vals  = r.throughput_7day

    score_labels  = ["9-10 💎", "8-9 🥇", "7-8 ⭐", "<7 🗑️"]
    score_values  = [r.score_dist.get(k, 0) for k in ["9-10","8-9","7-8","<7"]]
    score_colors  = ["#4ade80","#60a5fa","#facc15","#f87171"]

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

    if not pending_rows:
        pending_section = "<p style='color:var(--dim); padding:12px 0;'>当前无 pending 条目 ✅</p>"
    else:
        pending_section = f"""
        <table>
          <thead>
            <tr>
              <th>得分</th><th>标题</th><th>来源</th><th>日期</th><th>类型</th>
            </tr>
          </thead>
          <tbody>
            {pending_html}
          </tbody>
        </table>"""

    hc = "#4ade80" if r.health_score >= 80 else "#facc15" if r.health_score >= 50 else "#f87171"
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

    orphan_list_html = "".join(f'<li style="margin-bottom:4px; opacity:0.8;">• {name.replace("Axiom -","").strip()[:30]}</li>' for name in r.orphan_axioms[:4])
    if len(r.orphan_axioms) > 4:
        orphan_list_html += f'<li style="color:var(--dim);">...等 {len(r.orphan_axioms)-4} 条</li>'
    if not r.orphan_axioms:
        orphan_list_html = '<li style="color:var(--dim);">✅ 无孤立公理</li>'

    error_type_rows = ""
    if r.error_types:
        top_errors = sorted(r.error_types.items(), key=lambda x: x[1], reverse=True)[:5]
        for err_type, count in top_errors:
            error_type_rows += (
                f"<tr>"
                f"<td><code>{err_type}</code></td>"
                f"<td style='text-align:right; color: var(--red); font-weight: 700;'>{count}</td>"
                f"</tr>"
            )
    else:
        error_type_rows = "<tr><td style='color:var(--dim);'>暂无错误类型</td><td>0</td></tr>"

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
    font-family: 'Inter', sans-serif;
    font-size: 14px; line-height: 1.6; padding: 24px;
  }}
  h1 {{ font-size: 22px; font-weight: 700; color: var(--accent); }}
  h2 {{ font-size: 13px; font-weight: 600; color: var(--dim);
        text-transform: uppercase; letter-spacing: .08em; margin-bottom: 14px; }}
  .header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; }}
  .grid-4 {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; margin-bottom: 16px; }}
  .grid-2 {{ display: grid; grid-template-columns: repeat(2,1fr); gap: 16px; margin-bottom: 16px; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }}
  .kpi {{ text-align: center; }}
  .kpi .value {{ font-size: 36px; font-weight: 800; }}
  .kpi .label {{ color: var(--dim); font-size: 12px; }}
  .green {{ color: var(--green); }} .yellow {{ color: var(--yellow); }} .red {{ color: var(--red); }} .accent {{ color: var(--accent); }}
  .health-ring {{
    width: 100px; height: 100px; margin: 0 auto 12px; border-radius: 50%;
    background: conic-gradient({hc} {r.health_score:.0f}%, var(--border) 0);
    display: flex; align-items: center; justify-content: center; position: relative;
  }}
  .health-ring::after {{ content: ''; position: absolute; width: 75px; height: 75px; border-radius: 50%; background: var(--surface); }}
  .health-score {{ position: relative; z-index: 1; font-size: 22px; font-weight: 800; color: {hc}; }}
  .funnel-bar {{ margin-bottom: 8px; }}
  .funnel-label {{ display: flex; justify-content: space-between; font-size: 11px; color: var(--dim); margin-bottom: 2px; }}
  .funnel-track {{ background: var(--border); border-radius: 4px; height: 6px; overflow: hidden; }}
  .funnel-fill {{ height: 6px; transition: width .3s; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ color: var(--dim); font-size: 11px; text-transform: uppercase; padding: 6px 8px; text-align: left; border-bottom: 1px solid var(--border); }}
  td {{ padding: 8px 8px; border-bottom: 1px solid var(--border); font-size: 13px; }}
  .badge {{ border-radius: 5px; padding: 2px 7px; font-size: 11px; font-weight: 600; }}
  .badge-diamond {{ background: #052e16; color: #4ade80; }}
  .badge-gold {{ background: #1c1917; color: #fbbf24; }}
  .badge-silver {{ background: #0c1a2e; color: #60a5fa; }}
  .badge-bronze {{ background: #1c1917; color: #d1d5db; }}
  .bottleneck {{ background: rgba(248,113,113,.08); border: 1px solid rgba(248,113,113,.25); border-radius: 8px; padding: 8px; font-size: 12px; color: var(--red); margin-top: 8px; text-align: center; }}
  .bottleneck.ok {{ background: rgba(74,222,128,.08); border-color: rgba(74,222,128,.25); color: var(--green); }}
</style>
</head>
<body>
<div class="header">
  <div><h1>🚀 Antigravity OS</h1></div>
  <div style="text-align:right; color:var(--dim); font-size:12px;">{r.generated_at}</div>
</div>
<div class="grid-4">
  <div class="card kpi"><div class="value accent">{r.total}</div><div class="label">📥 总入库</div></div>
  <div class="card kpi"><div class="value yellow">{r.pending}</div><div class="label">⏳ Pending</div></div>
  <div class="card kpi"><div class="value green">{r.done}</div><div class="label">✅ 已完成</div></div>
  <div class="card kpi"><div class="value red">{r.error}</div><div class="label">❌ Error</div></div>
</div>
<div class="grid-4">
  <div class="card" style="text-align:center;">
    <h2>健康度</h2>
    <div class="health-ring"><span class="health-score">{r.health_score:.0f}</span></div>
    <div class="bottleneck {'ok' if r.health_score >= 80 else ''}">{r.bottleneck}</div>
  </div>
  <div class="card">
    <h2>Pipeline 漏斗</h2>
    <div class="funnel-bar">
      <div class="funnel-label"><span>✅ 完成</span><span>{pct_done:.0f}%</span></div>
      <div class="funnel-track"><div class="funnel-fill" style="width:{pct_done:.0f}%;background:var(--green)"></div></div>
    </div>
    <div class="funnel-bar">
      <div class="funnel-label"><span>⏳ Pending</span><span>{pct_pending:.0f}%</span></div>
      <div class="funnel-track"><div class="funnel-fill" style="width:{pct_pending:.0f}%;background:var(--yellow)"></div></div>
    </div>
    <div class="funnel-bar">
      <div class="funnel-label"><span>❌ Error</span><span>{pct_error:.0f}%</span></div>
      <div class="funnel-track"><div class="funnel-fill" style="width:{pct_error:.0f}%;background:var(--red)"></div></div>
    </div>
  </div>
  <div class="card">
    <h2>Cron 状态</h2>
    <table style="font-size:11px;">
       <tr><td>🤖 Bouncer</td><td>{fmt_dt(r.last_bouncer_run)}</td></tr>
       <tr><td>🧠 InboxProc</td><td>{fmt_dt(r.last_inbox_run)}</td></tr>
    </table>
    <canvas id="sparkChart" style="margin-top:10px;"></canvas>
  </div>
  <div class="card">
    <h2>🛡 知识库审计</h2>
    <div style="font-size:11px; margin-bottom:8px;">
      <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
        <span>🕸 孤儿 Axiom</span><span class="badge { 'badge-gold' if r.orphan_axioms else 'badge-diamond' }">{len(r.orphan_axioms)}</span>
      </div>
      <div style="display:flex; justify-content:space-between;">
        <span>⏳ 逾期积压</span><span class="badge { 'badge-bronze' if r.backlog_issues else 'badge-diamond' }">{len(r.backlog_issues)}</span>
      </div>
    </div>
    <ul style="list-style:none; font-size:10px; color:var(--text); border-top:1px solid var(--border); padding-top:8px;">
      {orphan_list_html}
    </ul>
  </div>
</div>
<div class="grid-2">
  <div class="card"><h2>7天趋势</h2><canvas id="trendChart"></canvas></div>
  <div class="card"><h2>分数分布</h2><canvas id="scoreChart"></canvas></div>
</div>
<div class="card">
  <h2>⏳ Pending 队列</h2>
  {pending_section}
</div>
<div class="card" style="margin-top:16px;">
  <h2>🧩 Error Types Top</h2>
  <table>
    <thead>
      <tr><th>错误类型</th><th style="text-align:right;">数量</th></tr>
    </thead>
    <tbody>
      {error_type_rows}
    </tbody>
  </table>
</div>
<script>
const DAYS = {json.dumps(days)};
const INBOX = {json.dumps(inbox_vals)};
const DONE = {json.dumps(done_vals)};
new Chart(document.getElementById('trendChart'), {{
  type: 'bar',
  data: {{
    labels: DAYS,
    datasets: [
      {{ label: '入库', data: INBOX, backgroundColor: 'rgba(96,165,250,0.3)', borderColor: '#60a5fa', borderWidth: 2, borderRadius: 4, type: 'bar' }},
      {{ label: '完成', data: DONE, borderColor: '#4ade80', backgroundColor: 'rgba(74,222,128,0.15)', borderWidth: 2, fill: true, type: 'line', tension: 0.3 }}
    ]
  }},
  options: {{ scales: {{ y: {{ beginAtZero: true, grid:{{color:'#1e293b'}}, ticks:{{color:'#64748b'}} }}, x:{{ grid:{{color:'#1e293b'}}, ticks:{{color:'#64748b'}} }} }} }}
}});
new Chart(document.getElementById('scoreChart'), {{
  type: 'doughnut',
  data: {{
    labels: {json.dumps(score_labels)},
    datasets: [{{ data: {json.dumps(score_values)}, backgroundColor: {json.dumps(score_colors)}, borderWidth: 0 }}]
  }},
  options: {{ plugins: {{ legend: {{ position: 'right', labels:{{color:'#94a3b8'}} }} }} }}
}});
new Chart(document.getElementById('sparkChart'), {{
  type: 'bar',
  data: {{ labels: DAYS, datasets: [ {{ data: INBOX, backgroundColor:'rgba(96,165,250,0.5)' }}, {{ data: DONE, backgroundColor:'rgba(74,222,128,0.5)' }} ] }},
  options: {{ plugins:{{legend:{{display:false}}}}, scales:{{ x:{{display:false}}, y:{{display:false}} }} }}
}});
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="生成 Antigravity OS HTML 报告")
    parser.add_argument("--out",       default=str(DEFAULT_OUT), help="输出路径")
    parser.add_argument("--no-open",   action="store_true",      help="不自动打开浏览器")
    args = parser.parse_args()
    r = collect()
    html = render_html(r)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"✅ 报告已生成: {out}")
    if not args.no_open:
        subprocess.run(["open", str(out)], check=False)


if __name__ == "__main__":
    main()
