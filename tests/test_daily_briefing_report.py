"""daily_briefing 报告内容测试。"""

from types import SimpleNamespace
from datetime import datetime, timedelta

from agents.daily_briefing.daily_briefing import build_report, BACKLOG_THRESHOLD_DAYS


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


def test_build_report_uses_configurable_backlog_days():
    r = SimpleNamespace(
        health_score=70.0,
        orphan_axioms=[],
        backlog_issues=[{"title": "x", "days": BACKLOG_THRESHOLD_DAYS + 1, "score": 8.1}],
        error=0,
        error_types={},
        total=1,
        pending=1,
        done=0,
        bottleneck="⏳ Pending 积压",
        notes=[],
        last_bouncer_run=None,
        last_inbox_run=None,
        bouncer_7day=[0, 0, 0, 0, 0, 0, 1],
        throughput_7day=[0, 0, 0, 0, 0, 0, 0],
    )
    text = build_report(r)
    assert f"超过 {BACKLOG_THRESHOLD_DAYS} 天" in text


def test_build_report_flags_stale_cron():
    r = SimpleNamespace(
        health_score=88.0,
        orphan_axioms=[],
        backlog_issues=[],
        error=0,
        error_types={},
        total=5,
        pending=1,
        done=4,
        bottleneck="",
        notes=[],
        last_bouncer_run=datetime.now() - timedelta(hours=30),
        last_inbox_run=None,
        bouncer_7day=[1, 1, 0, 0, 1, 0, 1],
        throughput_7day=[1, 0, 0, 0, 1, 0, 0],
    )
    text = build_report(r)
    assert "Bouncer 超过 26h 未成功运行" in text
    assert "Inbox Processor 超过 26h 未成功运行" in text


def test_build_report_uses_idle_hours_if_present():
    old = datetime.now() - timedelta(hours=48)
    r = SimpleNamespace(
        health_score=90.0,
        orphan_axioms=[],
        backlog_issues=[],
        error=0,
        error_types={},
        total=3,
        pending=1,
        done=2,
        bottleneck="",
        notes=[],
        last_bouncer_run=old,
        last_inbox_run=old,
        bouncer_idle_hours=2.0,
        inbox_idle_hours=3.0,
        bouncer_7day=[0, 0, 0, 1, 0, 0, 1],
        throughput_7day=[0, 0, 0, 1, 0, 0, 1],
    )
    text = build_report(r)
    assert "Bouncer 超过 26h 未成功运行" not in text
    assert "Inbox Processor 超过 26h 未成功运行" not in text
