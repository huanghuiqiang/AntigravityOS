"""daily_briefing 报告内容测试。"""

from types import SimpleNamespace

from agents.daily_briefing.daily_briefing import build_report


def test_build_report_includes_error_type_top():
    r = SimpleNamespace(
        health_score=78.0,
        orphan_axioms=[],
        backlog_issues=[],
        error=3,
        error_types={"report_wait_timeout": 2, "report_download_failed": 1},
        total=10,
        pending=2,
        done=8,
        bottleneck="❌ Error 率 30%",
        notes=[],
        last_bouncer_run=None,
        last_inbox_run=None,
        bouncer_7day=[1, 1, 2, 0, 3, 1, 2],
        throughput_7day=[1, 0, 1, 0, 2, 1, 1],
    )

    text = build_report(r)
    assert "失败类型 Top" in text
    assert "<code>report_wait_timeout</code>: 2" in text
    assert "<code>report_download_failed</code>: 1" in text
