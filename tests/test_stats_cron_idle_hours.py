"""stats cron idle hours 字段测试。"""

from scripts import stats


def test_collect_sets_cron_idle_hours_from_logs(tmp_path, monkeypatch):
    bouncer_log = tmp_path / "bouncer.log"
    inbox_log = tmp_path / "inbox_processor.log"
    bouncer_log.write_text("共审查 1 篇\n高认知密度文章: 1\n", encoding="utf-8")
    inbox_log.write_text("inbox ok\n", encoding="utf-8")

    monkeypatch.setattr(stats, "_bouncer_log_candidates", lambda: [bouncer_log])
    monkeypatch.setattr(stats, "_inbox_log_candidates", lambda: [inbox_log])

    report = stats.collect()
    assert report.last_bouncer_run is not None
    assert report.last_inbox_run is not None
    assert report.bouncer_idle_hours >= 0
    assert report.inbox_idle_hours >= 0
