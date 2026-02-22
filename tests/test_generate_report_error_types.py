"""generate_report 错误类型可视化测试。"""

from types import SimpleNamespace

from scripts.generate_report import render_html


def test_render_html_includes_error_type_top():
    report = SimpleNamespace(
        generated_at="2026-02-22 19:00:00",
        bouncer_7day=[1, 2, 1, 3, 0, 2, 1],
        throughput_7day=[1, 1, 1, 2, 0, 1, 1],
        score_dist={"9-10": 2, "8-9": 3, "7-8": 1, "<7": 0},
        notes=[],
        health_score=82.0,
        total=10,
        pending=2,
        done=7,
        error=1,
        bottleneck="❌ Error 率 10%",
        last_bouncer_run=None,
        last_inbox_run=None,
        orphan_axioms=[],
        backlog_issues=[],
        error_types={"report_wait_timeout": 3, "report_download_failed": 1},
    )

    html = render_html(report)
    assert "Error Types Top" in html
    assert "<code>report_wait_timeout</code>" in html
    assert ">3<" in html
