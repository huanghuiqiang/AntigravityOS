"""stats 错误类型聚合测试。"""

from scripts.stats import collect


def test_collect_aggregates_error_types(tmp_vault):
    inbox = tmp_vault / "00_Inbox"
    err_note = inbox / "Bouncer - Error Case.md"
    err_note.write_text(
        """---
tags:
  - BouncerDump
score: 8.4
status: error
error: "download failed"
error_type: "report_download_failed"
source: "https://example.com/e"
title: "Error Case"
created: "2026-02-22"
---

# Error Case
""",
        encoding="utf-8",
    )

    report = collect()
    assert report.error >= 1
    assert report.error_types.get("report_download_failed", 0) >= 1
