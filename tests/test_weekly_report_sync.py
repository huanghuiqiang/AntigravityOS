"""weekly_report_sync 周报飞书同步测试。"""

from datetime import datetime
from types import SimpleNamespace

from agents.daily_briefing import weekly_report_sync as wr


def _mock_report():
    return SimpleNamespace(
        health_score=86.0,
        total=40,
        pending=7,
        done=31,
        error=2,
        bouncer_7day=[5, 6, 4, 7, 8, 4, 6],
        throughput_7day=[4, 4, 3, 5, 6, 3, 5],
        bottleneck="⏳ Pending 积压",
        error_types={"report_wait_timeout": 2, "unknown_error": 1},
    )


def test_build_weekly_markdown_contains_metrics():
    text = wr._build_weekly_markdown(_mock_report(), today=datetime(2026, 2, 23))
    assert "Antigravity 周报" in text
    assert "系统健康度：86/100" in text
    assert "7日入库总量" in text
    assert "`report_wait_timeout`: 2" in text


def test_sync_weekly_report_creates_subdoc_and_appends(monkeypatch):
    calls = []

    class _FakeBridge:
        def create_sub_doc(self, title: str, folder_token=None):
            calls.append(("create", title))
            return {"document_id": "doc_weekly_1", "url": "https://x/doc_weekly_1"}

        def append_markdown(self, markdown: str, section_title=None, document_id=None):
            calls.append(("append", markdown, section_title, document_id))
            return {"success": True}

    monkeypatch.setattr(wr, "collect", _mock_report)
    result = wr.sync_weekly_report(bridge=_FakeBridge(), today=datetime(2026, 2, 23))

    assert result["success"] is True
    assert calls[0][0] == "create"
    assert calls[1][0] == "append"
    assert calls[1][3] == "doc_weekly_1"
    assert calls[2][0] == "append"
    assert calls[2][2] is not None
    assert calls[2][3] is None

