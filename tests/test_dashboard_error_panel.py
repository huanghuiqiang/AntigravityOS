"""dashboard 错误类型面板渲染测试。"""

from types import SimpleNamespace

import pytest

pytest.importorskip("rich")

from rich.console import Console

from scripts.dashboard import build_error_panel


def test_build_error_panel_renders_error_types():
    report = SimpleNamespace(error_types={"report_wait_timeout": 3, "report_download_failed": 1})
    panel = build_error_panel(report)

    console = Console(record=True, width=120)
    console.print(panel)
    text = console.export_text()

    assert "Error Types" in text
    assert "report_wait_timeout" in text
    assert "3" in text
