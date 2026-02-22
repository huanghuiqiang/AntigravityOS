"""stats 结构化告警输出测试。"""

import json
import os
import time

from scripts import stats


def test_warn_outputs_json(capsys):
    stats._warn("stats/test", "something happened")
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["level"] == "WARN"
    assert payload["scope"] == "stats/test"
    assert payload["detail"] == "something happened"
    assert "ts" in payload


def test_warn_outputs_error_fields(capsys):
    stats._warn("stats/test", "failed", ValueError("bad value"))
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["error"] == "bad value"
    assert payload["error_type"] == "ValueError"


def test_collect_warns_when_auditor_unavailable(monkeypatch, capsys):
    monkeypatch.setattr(stats, "_load_auditor", lambda: (_ for _ in ()).throw(RuntimeError("auditor boom")))
    report = stats.collect()
    assert report is not None
    out = capsys.readouterr().out.strip().splitlines()
    payload = json.loads(out[-1])
    assert payload["scope"] == "stats/auditor"
    assert payload["error_type"] == "RuntimeError"


def test_parse_bouncer_log_falls_back_to_legacy_name(tmp_path, monkeypatch):
    legacy = tmp_path / "cognitive_bouncer.log"
    legacy.write_text("✅ 巡逻完成。共审查 5 篇\n高认知密度文章: 2\n", encoding="utf-8")
    monkeypatch.setattr(stats, "_bouncer_log_candidates", lambda: [tmp_path / "bouncer.log", legacy])

    runs = stats._parse_bouncer_log()
    assert len(runs) == 1
    assert runs[0].scanned == 5
    assert runs[0].golden == 2


def test_pick_latest_existing_prefers_newer_file(tmp_path):
    a = tmp_path / "a.log"
    b = tmp_path / "b.log"
    a.write_text("a", encoding="utf-8")
    b.write_text("b", encoding="utf-8")
    now = time.time()
    # Ensure deterministic ordering by mtime.
    os.utime(a, (now - 10, now - 10))
    os.utime(b, (now, now))
    picked = stats._pick_latest_existing([a, b])
    assert picked == b
