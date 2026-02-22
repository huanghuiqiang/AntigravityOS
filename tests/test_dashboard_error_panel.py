"""dashboard 错误类型面板渲染测试。"""

from types import SimpleNamespace

import pytest

pytest.importorskip("rich")

from rich.console import Console

from datetime import datetime, timedelta

from scripts.dashboard import build_error_panel, build_cron_panel


def test_build_error_panel_renders_error_types():
    report = SimpleNamespace(error_types={"report_wait_timeout": 3, "report_download_failed": 1})
    panel = build_error_panel(report)

    console = Console(record=True, width=120)
    console.print(panel)
    text = console.export_text()

    assert "Error Types" in text
    assert "report_wait_timeout" in text
    assert "3" in text


def test_build_cron_panel_prefers_idle_hours():
    old = datetime.now() - timedelta(hours=48)
    report = SimpleNamespace(
        last_bouncer_run=old,
        last_inbox_run=old,
        bouncer_idle_hours=2.0,
        inbox_idle_hours=3.0,
        bouncer_7day=[0, 0, 0, 0, 0, 0, 1],
        throughput_7day=[0, 0, 0, 0, 0, 0, 1],
    )
    panel = build_cron_panel(report)
    console = Console(record=True, width=120)
    console.print(panel)
    text = console.export_text()
    assert "(2h 前)" in text
    assert "(3h 前)" in text
