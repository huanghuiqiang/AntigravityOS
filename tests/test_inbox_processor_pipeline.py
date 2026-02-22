"""inbox_processor 关键路径测试。"""

from agents.inbox_processor.inbox_processor import _run, process_note, build_telegram_report


def test_run_returns_127_for_missing_binary():
    rc, out, err = _run(["definitely_missing_cmd_12345"], timeout=1)
    assert rc == 127
    assert out == ""
    assert "命令不存在" in err


def test_process_note_dry_run(tmp_vault):
    note = {
        "path": str(tmp_vault / "00_Inbox" / "Bouncer - Test Article.md"),
        "title": "Test Article",
        "score": 9.2,
        "source": "https://example.com/article",
    }
    result = process_note(note, dry_run=True)
    assert result["success"] is True
    assert result["title"] == "Test Article"
    assert result["note_path"].endswith("Bouncer - Test Article.md")
    assert result["source_url"] == "https://example.com/article"
    assert result["error_type"] == ""


def test_telegram_report_groups_failure_types():
    results = [
        {"success": True, "score": 9.5, "title": "A", "notebook_id": "nb1"},
        {"success": False, "score": 8.8, "title": "B", "error": "timeout", "error_type": "report_wait_timeout"},
        {"success": False, "score": 8.6, "title": "C", "error": "timeout2", "error_type": "report_wait_timeout"},
        {"success": False, "score": 8.2, "title": "D", "error": "parse fail", "error_type": "report_task_parse_failed"},
    ]
    text = build_telegram_report(results, total_pending=10)
    assert "失败类型统计" in text
    assert "<code>report_wait_timeout</code>: 2" in text
    assert "<code>report_task_parse_failed</code>: 1" in text
