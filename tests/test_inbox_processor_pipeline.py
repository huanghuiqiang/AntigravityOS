"""inbox_processor 关键路径测试。"""

from agents.inbox_processor.inbox_processor import _run, process_note


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
