"""inbox_processor -> stats -> daily_briefing 错误类型联动测试。"""

from pathlib import Path

from agents.inbox_processor import inbox_processor
from agents.daily_briefing.daily_briefing import build_report
from scripts.stats import collect


def test_error_type_flows_from_processor_to_briefing(tmp_vault, monkeypatch):
    note_path = tmp_vault / "00_Inbox" / "Bouncer - Test Article.md"
    note = {
        "path": str(note_path),
        "title": "Test Article",
        "score": 9.2,
        "source": "https://example.com/article",
    }

    def _fake_nlm(*args, **kwargs):
        return {
            "success": False,
            "error": "mock timeout",
            "error_type": "report_wait_timeout",
            "notebook_id": "",
            "note_path": str(note_path),
            "source_url": "https://example.com/article",
        }

    monkeypatch.setattr(inbox_processor, "process_with_notebooklm", _fake_nlm)

    outcome = inbox_processor.process_note(note, dry_run=False)
    assert outcome["success"] is False
    assert outcome["error_type"] == "report_wait_timeout"

    report = collect()
    assert report.error >= 1
    assert report.error_types.get("report_wait_timeout", 0) >= 1

    briefing = build_report(report)
    assert "失败类型 Top" in briefing
    assert "report_wait_timeout" in briefing
